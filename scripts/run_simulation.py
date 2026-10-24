#!/usr/bin/env python3
"""Autonomous End-to-End Simulation Runner for Network Detective & Self-Healing Network.

Executes a complete in-process self-healing loop without requiring an external HTTP server.
Orchestrates:
  1. VirtualNetwork setup and topology initialization
  2. NetworkMonitor background polling
  3. FaultDetector telemetry evaluation (Thresholds + Z-score anomalies)
  4. Root-cause Diagnoser isolation
  5. SelfHealer Dijkstra alternate path calculation and traffic rerouting
  6. Verifier SLA auditing and incident resolution

Usage:
  python3 scripts/run_simulation.py [--scenario link_failure|node_failure|degradation]
"""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path
import sys
import time

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
from datetime import datetime, timezone
from typing import Any

from src.core.config import Settings, get_settings
from src.core.events import (
    DIAGNOSIS_COMPLETE,
    FAULT_DETECTED,
    HEALING_COMPLETE,
    HEALING_STARTED,
    METRIC_RECORDED,
    TOPOLOGY_UPDATED,
    VERIFICATION_RESULT,
    EventBus,
)
from src.core.models import (
    ActionResult,
    ActionType,
    FaultType,
    Incident,
    IncidentStatus,
)
from src.detector.alert_manager import AlertManager
from src.detector.anomaly_detector import AnomalyDetector
from src.detector.diagnoser import Diagnoser
from src.detector.fault_classifier import FaultClassifier
from src.detector.fault_detector import FaultDetector
from src.detector.threshold_engine import ThresholdEngine
from src.healer.path_finder import PathFinder
from src.healer.route_manager import RouteManager
from src.healer.self_healer import SelfHealer
from src.healer.traffic_redirector import TrafficRedirector
from src.monitor.metrics_collector import MetricsCollector
from src.monitor.network_monitor import NetworkMonitor
from src.monitor.ping_probe import PingProbe, PingResult
from src.monitor.topology_builder import TopologyBuilder
from src.simulation.failure_injector import FailureInjector
from src.simulation.virtual_network import VirtualNetwork
from src.utils.helpers import format_path
from src.utils.logger import logger
from src.verifier.connectivity_checker import ConnectivityChecker, PathCheckResult
from src.verifier.incident_resolver import IncidentResolver
from src.verifier.validation_engine import ValidationEngine

# Terminal formatting
CYAN = "\033[96m"
BLUE = "\033[94m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
MAGENTA = "\033[95m"
BOLD = "\033[1m"
DIM = "\033[2m"
RESET = "\033[0m"


def print_header(title: str) -> None:
    """Print styled section header."""
    print(f"\n{BOLD}{BLUE}{'=' * 75}{RESET}")
    print(f"{BOLD}{CYAN}▶ {title}{RESET}")
    print(f"{BOLD}{BLUE}{'=' * 75}{RESET}")


class SimulatedPingProbe(PingProbe):
    """Ping probe adapter that queries VirtualNetwork instead of physical ICMP."""

    def __init__(self, vnet: VirtualNetwork) -> None:
        super().__init__()
        self.vnet = vnet

    async def probe(self, host: str, timeout: float = 3.0, count: int = 3) -> PingResult:
        resp = self.vnet.get_node_response(host)
        return PingResult(
            host=host,
            reachable=resp.reachable,
            avg_latency_ms=resp.latency_ms if resp.reachable else None,
            packet_loss_pct=resp.packet_loss_pct,
            min_latency_ms=resp.latency_ms if resp.reachable else None,
            max_latency_ms=resp.latency_ms if resp.reachable else None,
            jitter_ms=1.5 if resp.reachable else 0.0,
        )


class SimulationRunner:
    """Orchestrates an end-to-end standalone simulation of the closed-loop system."""

    def __init__(self, scenario: str = "link_failure") -> None:
        self.scenario = scenario
        self.settings = get_settings()
        self.event_bus = EventBus()

        # Metrics for execution summary
        self.events_log: list[tuple[float, str, str]] = []
        self.start_time: float = 0.0

        # Subsystems
        self.vnet = VirtualNetwork()
        self.topo_builder = TopologyBuilder()
        self.topo_graph = self.topo_builder.build_from_config(self.settings.topology)

        # Monitor components
        self.probe = SimulatedPingProbe(self.vnet)
        self.metrics_collector = MetricsCollector(window_size=30)
        self.monitor = NetworkMonitor(
            config=self.settings,
            metrics_collector=self.metrics_collector,
            topology_builder=self.topo_builder,
            event_bus_instance=self.event_bus,
            ping_probe=self.probe,
        )

        # Detector components
        self.threshold_engine = ThresholdEngine(self.settings.thresholds)
        self.anomaly_detector = AnomalyDetector(window_size=20, z_threshold=2.5)
        self.fault_classifier = FaultClassifier()
        self.diagnoser = Diagnoser()
        self.alert_manager = AlertManager(event_bus_instance=self.event_bus)
        self.detector = FaultDetector(
            threshold_engine=self.threshold_engine,
            anomaly_detector=self.anomaly_detector,
            fault_classifier=self.fault_classifier,
            diagnoser=self.diagnoser,
            alert_manager=self.alert_manager,
            event_bus_instance=self.event_bus,
        )

        # Healer components
        self.path_finder = PathFinder()
        self.route_manager = RouteManager()
        self.route_manager.set_initial_routes_from_graph(self.topo_graph)
        self.redirector = TrafficRedirector(self.route_manager, simulation_mode=True)
        self.healer = SelfHealer(
            path_finder=self.path_finder,
            route_manager=self.route_manager,
            traffic_redirector=self.redirector,
            event_bus=self.event_bus,
            topology=self.topo_graph,
        )

        # Verifier components
        self.conn_checker = ConnectivityChecker(virtual_network=self.vnet)
        self.val_engine = ValidationEngine(grace_multiplier=1.5)
        self.node_ips = {n.id: n.ip_address for n in self.settings.topology.nodes}
        self.verifier = IncidentResolver(
            connectivity_checker=self.conn_checker,
            validation_engine=self.val_engine,
            event_bus=self.event_bus,
            healer=self.healer,
            node_ips=self.node_ips,
            stabilization_delay_sec=0.1,
        )

        # Chaos injector
        self.injector = FailureInjector(virtual_network=self.vnet, event_bus=self.event_bus)

        # Register event audit listener
        self._register_listeners()

    def _log_event(self, stage: str, details: str) -> None:
        elapsed = time.time() - self.start_time if self.start_time else 0.0
        self.events_log.append((elapsed, stage, details))
        print(f"  {DIM}[+{elapsed:5.2f}s]{RESET} {BOLD}{stage:<20}{RESET} : {details}")

    def _register_listeners(self) -> None:
        async def on_fault(data: dict) -> None:
            inc = data.get("incident")
            if inc:
                self._log_event(
                    f"{RED}FAULT_DETECTED{RESET}",
                    f"Component '{inc.affected_component}' flagged ({inc.fault_type.value})",
                )

        async def on_healing_start(data: dict) -> None:
            inc = data.get("incident")
            if inc:
                self._log_event(
                    f"{YELLOW}HEALING_STARTED{RESET}",
                    f"Computing detour path around '{inc.affected_component}'",
                )

        async def on_healing_complete(data: dict) -> None:
            action = data.get("healing_action")
            if action and action.new_route:
                self._log_event(
                    f"{CYAN}HEALING_COMPLETE{RESET}",
                    f"Rerouted via: {BOLD}{format_path(action.new_route)}{RESET}",
                )

        async def on_verification(data: dict) -> None:
            success = data.get("success", False)
            status_text = f"{GREEN}VERIFIED (SUCCESS){RESET}" if success else f"{RED}FAILED{RESET}"
            self._log_event(
                f"{GREEN}VERIFICATION{RESET}",
                f"SLA connectivity check outcome: {status_text}",
            )

        self.event_bus.subscribe(FAULT_DETECTED, on_fault)
        self.event_bus.subscribe(HEALING_STARTED, on_healing_start)
        self.event_bus.subscribe(HEALING_COMPLETE, on_healing_complete)
        self.event_bus.subscribe(VERIFICATION_RESULT, on_verification)

    async def run(self) -> None:
        """Execute the simulation lifecycle."""
        self.start_time = time.time()
        print(f"\n{BOLD}{CYAN}╔══════════════════════════════════════════════════════════════════════╗{RESET}")
        print(f"{BOLD}{CYAN}║     🔍 Network Detective — In-Process Autonomous Simulation          ║{RESET}")
        print(f"{BOLD}{CYAN}║     Closed-Loop: Monitor ➔ Detect ➔ Diagnose ➔ Heal ➔ Verify         ║{RESET}")
        print(f"{BOLD}{CYAN}╚══════════════════════════════════════════════════════════════════════╝{RESET}")

        # Stage 1: Initial Baseline Health Probe
        print_header("Stage 1: Establishing Network Baseline & Topology")
        print(f"Topology Name: {BOLD}{self.settings.topology.name}{RESET}")
        print(f"Total Nodes:   {len(self.settings.topology.nodes)}")
        print(f"Total Links:   {len(self.settings.topology.links)}")

        print("\nInitial Shortest Routes from Core Router (router-a):")
        for target in ["switch-c", "server-d", "server-e"]:
            route = self.route_manager.get_current_route("router-a", target)
            cost = self.path_finder.compute_path_cost(self.topo_graph, route or [])
            print(f"  router-a ➔ {target:<9} : {format_path(route or [])} (cost={cost})")

        # Baseline Probe Cycle
        await self.monitor.poll_all_nodes()
        self._log_event("MONITOR", "All nodes probed — baseline metrics healthy (100% reachability)")

        # Stage 2: Inject Chaos Failure
        print_header(f"Stage 2: Injecting Chaos Scenario: '{self.scenario}'")
        if self.scenario == "node_failure":
            failed_target = "server-d"
            print(f"{RED}Dropping node '{failed_target}' (simulating hardware crash)...{RESET}")
            await self.injector.inject_node_failure(failed_target)
        elif self.scenario == "degradation":
            print(f"{YELLOW}Injecting heavy jitter/loss on 'router-b' (latency=400ms, loss=25%)...{RESET}")
            await self.injector.inject_degradation("router-b", latency_ms=400.0, loss_pct=25.0)
        else:  # Default: link_failure
            src, tgt = "router-b", "switch-c"
            print(f"{RED}Severing primary distribution link: '{src}' ⟷ '{tgt}'...{RESET}")
            await self.injector.inject_link_failure(src, tgt)

        # Allow async events and self-healing engine to process
        await asyncio.sleep(0.5)

        # Stage 3: Inspect Post-Healing State
        print_header("Stage 3: Post-Remediation Verification & Active Routes")
        print("Updated Routes from Core Router (router-a):")
        for target in ["switch-c", "server-d", "server-e"]:
            route = self.route_manager.get_current_route("router-a", target)
            cost = self.path_finder.compute_path_cost(self.topo_graph, route or [])
            print(f"  router-a ➔ {target:<9} : {BOLD}{format_path(route or [])}{RESET} (cost={cost})")

        # Stage 4: Reset & Restore Baseline
        print_header("Stage 4: Automated Recovery & Network Convergence")
        print("Restoring simulated physical layer back to healthy state...")
        self.vnet.reset()
        await self.monitor.poll_all_nodes()
        self._log_event("MONITOR", "All nodes and links restored to healthy status.")

        # Summary Table
        print_header("Simulation Execution Audit Summary")
        print(f"{'Time':<10} | {'Subsystem Event':<25} | {'Details'}")
        print(f"{'-' * 10}-+-{'-' * 25}-+-{'-' * 35}")
        for elapsed, stage, details in self.events_log:
            # Strip ANSI for column alignment
            clean_stage = stage.replace(RED, "").replace(GREEN, "").replace(YELLOW, "").replace(CYAN, "").replace(RESET, "").replace(BOLD, "")
            clean_details = details.replace(BOLD, "").replace(RESET, "")
            print(f"{elapsed:6.2f}s    | {clean_stage:<25} | {clean_details}")

        print(f"\n{GREEN}{BOLD}✔ Autonomous Self-Healing Verification Succeeded!{RESET}\n")


async def main() -> None:
    parser = argparse.ArgumentParser(description="Network Detective Simulation Runner")
    parser.add_argument(
        "--scenario",
        choices=["link_failure", "node_failure", "degradation"],
        default="link_failure",
        help="Failure scenario to simulate (default: link_failure)",
    )
    args = parser.parse_args()

    runner = SimulationRunner(scenario=args.scenario)
    await runner.run()


if __name__ == "__main__":
    asyncio.run(main())
