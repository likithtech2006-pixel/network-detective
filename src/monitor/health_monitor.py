"""Continuous health monitoring of the simulated network.

Every cycle the monitor probes each node and each link of the VirtualNetwork, checks the
samples against the configured thresholds, and confirms a failure only after it has been
seen on several consecutive cycles. Newly confirmed failures go through the Diagnoser so a
crashed device is reported once (not once per attached link), and the AlertManager then
raises the incident that starts the self-healing loop. When a component becomes healthy
again, its status is restored, routes fail back to the primary paths and its incident is
closed.
"""

from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone
from typing import Any

import networkx as nx
from sqlalchemy import func, update

from src.core.events import METRIC_RECORDED, TOPOLOGY_UPDATED, EventBus
from src.core.events import event_bus as default_event_bus
from src.core.models import (
    Database,
    FaultType,
    Incident,
    Link,
    LinkStatus,
    Node,
    NodeStatus,
)
from src.detector.alert_manager import AlertManager
from src.detector.diagnoser import Diagnoser
from src.detector.fault_classifier import Fault
from src.detector.threshold_engine import ThresholdEngine
from src.healer.route_manager import RouteManager
from src.monitor.live_probe import LiveProber
from src.monitor.metrics_collector import MetricsCollector
from src.monitor.topology_builder import TopologyBuilder, get_topology
from src.simulation.virtual_network import VirtualNetwork
from src.utils.logger import logger

SIMULATION = "simulation"
LIVE = "live"


class HealthMonitor:
    """Probes the network on a fixed interval and raises confirmed faults.

    In simulation mode devices and links are read from the VirtualNetwork. In live mode
    every device is pinged at its real IP address; links stay logical (a ping cannot test
    one cable), so a link counts as down when it is cut in the simulator or either end
    stops answering.
    """

    def __init__(
        self,
        virtual_network: VirtualNetwork,
        alert_manager: AlertManager,
        route_manager: RouteManager,
        db: Database,
        diagnoser: Diagnoser | None = None,
        threshold_engine: ThresholdEngine | None = None,
        metrics_collector: MetricsCollector | None = None,
        event_bus: EventBus | None = None,
        interval_sec: float = 0.5,
        confirmations: int = 3,
        metric_every_sec: float = 2.0,
        live_prober: LiveProber | None = None,
        live_interval_sec: float = 1.0,
    ) -> None:
        """Initialize the monitor.

        Args:
            virtual_network: Simulated network to probe.
            alert_manager: Raises incidents (and FAULT_DETECTED) for diagnosed faults.
            route_manager: Routing table to rebuild when components recover.
            db: Database for node, link and incident status updates.
            diagnoser: Root-cause analysis over the faults confirmed in one cycle.
            threshold_engine: Latency and packet-loss threshold checks.
            metrics_collector: Stores node telemetry for the Metrics page.
            event_bus: Bus for METRIC_RECORDED and TOPOLOGY_UPDATED events.
            interval_sec: Seconds between probe cycles.
            confirmations: Consecutive bad samples needed before a failure counts.
            metric_every_sec: How often telemetry is stored and broadcast.
            live_prober: Pings real devices in live mode.
            live_interval_sec: Seconds between probe cycles in live mode.
        """
        self.virtual_network = virtual_network
        self.alert_manager = alert_manager
        self.route_manager = route_manager
        self.db = db
        self.diagnoser = diagnoser or Diagnoser()
        self.threshold_engine = threshold_engine or ThresholdEngine()
        self.metrics_collector = metrics_collector or MetricsCollector(db=db)
        self.event_bus = event_bus or default_event_bus
        self.sim_interval_sec = interval_sec
        self.live_interval_sec = live_interval_sec
        self.interval_sec = interval_sec
        self.confirmations = max(1, confirmations)
        self.metric_every_sec = metric_every_sec
        self.live_prober = live_prober or LiveProber()
        self.mode = SIMULATION

        self._builder = TopologyBuilder()
        # Consecutive bad samples per component (node ID or link ID)
        self._streak: dict[str, int] = {}
        # Confirmed faulty component -> the root cause it was reported under
        self._faulty: dict[str, str] = {}
        # When each component first looked bad in its current streak (for detection time)
        self._first_bad_at: dict[str, float] = {}
        self._last_metrics_at = 0.0
        # Previous answered latency per device, for jitter (RFC 3550 style difference)
        self._last_latency: dict[str, float] = {}
        self._lock = asyncio.Lock()
        self._task: asyncio.Task[None] | None = None
        self._background: set[asyncio.Task[None]] = set()

    @staticmethod
    def link_id(source: str, target: str) -> str:
        """Component ID used for a link in faults and incidents."""
        return f"link-{source}-{target}"

    def start(self) -> None:
        """Start the background probe loop."""
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._run(), name="health-monitor")
            logger.info(
                "HealthMonitor started: every {}s, {} confirmations per failure.",
                self.interval_sec,
                self.confirmations,
            )

    async def stop(self) -> None:
        """Stop the background probe loop."""
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def reset(self) -> None:
        """Forget all failure state (the network was reset to healthy by hand)."""
        async with self._lock:
            self._streak.clear()
            self._faulty.clear()
            self._first_bad_at.clear()

    async def set_mode(self, mode: str) -> None:
        """Switch between probing the simulation and pinging real devices.

        Args:
            mode: "simulation" or "live".
        """
        if mode not in (SIMULATION, LIVE):
            raise ValueError(f"Unknown network mode '{mode}'")
        await self.reset()
        self.mode = mode
        self.interval_sec = self.live_interval_sec if mode == LIVE else self.sim_interval_sec
        logger.info("HealthMonitor now in {} mode (every {}s).", mode, self.interval_sec)

    async def forget(self, nodes: set[str], links: set[tuple[str, str]]) -> None:
        """Drop failure state for devices and wires that were removed from the topology.

        Args:
            nodes: Removed device IDs (their wires are dropped too).
            links: Removed wires as (source, target) pairs.
        """
        gone = set(nodes)
        gone |= {self.link_id(u, v) for u, v in links} | {self.link_id(v, u) for u, v in links}
        async with self._lock:
            for component in list(self._streak):
                touches_node = any(
                    component.startswith(f"link-{n}-") or component.endswith(f"-{n}") for n in nodes
                )
                if component in gone or touches_node:
                    self._streak.pop(component, None)
                    self._first_bad_at.pop(component, None)
                    root = self._faulty.pop(component, None)
                    if root == component:
                        self.alert_manager.release_component(component)

    async def _run(self) -> None:
        while True:
            try:
                await self.poll_once()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.exception("HealthMonitor cycle failed: {}", exc)
            await asyncio.sleep(self.interval_sec)

    async def poll_once(self) -> None:
        """Run one probe cycle: sample, confirm, diagnose, alert, and handle recoveries."""
        async with self._lock:
            graph = get_topology()
            now = time.monotonic()
            bad = await self._sample(graph, now)

            for component in list(self._streak):
                if component not in bad:
                    self._streak[component] = 0
                    self._first_bad_at.pop(component, None)
            for component in bad:
                self._streak[component] = self._streak.get(component, 0) + 1
                self._first_bad_at.setdefault(component, now)

            confirmed = {
                component: fault
                for component, fault in bad.items()
                if self._streak[component] >= self.confirmations and component not in self._faulty
            }
            if confirmed:
                await self._raise_faults(graph, confirmed, now)

            recovered_roots = {root for comp, root in self._faulty.items() if comp == root}
            for root in recovered_roots:
                if root not in bad:
                    await self._recover(graph, root, bad)

    async def _sample(self, graph: nx.Graph, now: float) -> dict[str, Fault]:
        """Probe every node and link once; return the components that look unhealthy."""
        bad: dict[str, Fault] = {}
        reachable: dict[str, bool] = {}
        samples: list[dict[str, Any]] = []

        if self.mode == LIVE:
            hosts = {n: str(graph.nodes[n].get("ip_address") or n) for n in graph.nodes}
            responses: dict[str, Any] = await self.live_prober.ping_many(hosts)
        else:
            responses = {n: self.virtual_network.get_node_response(n) for n in graph.nodes}

        for node_id in graph.nodes:
            resp = responses[node_id]
            reachable[node_id] = resp.reachable
            violations = self.threshold_engine.check(
                node_id=node_id,
                latency_ms=resp.latency_ms,
                packet_loss_pct=resp.packet_loss_pct,
                reachable=resp.reachable,
                consecutive_failures=self._streak.get(node_id, 0) + 1,
            )
            critical = [v for v in violations if v.severity == "critical"]
            if not resp.reachable:
                bad[node_id] = Fault(FaultType.NODE_DOWN, node_id, "critical", 0.95)
            elif critical:
                bad[node_id] = Fault(critical[0].violation_type, node_id, "critical", 0.9)
            samples.append(
                {
                    "node_id": node_id,
                    "latency_ms": resp.latency_ms,
                    "packet_loss_pct": resp.packet_loss_pct,
                    "reachable": resp.reachable,
                    "status": resp.status,
                }
            )

        for u, v in graph.edges:
            # Wires are logical in both modes: cut in the simulator, or an end not answering
            resp = self.virtual_network.get_link_response(u, v)
            if not (resp.reachable and reachable.get(u) and reachable.get(v)):
                link = self.link_id(u, v)
                bad[link] = Fault(FaultType.LINK_DOWN, link, "critical", 0.9)

        if now - self._last_metrics_at >= self.metric_every_sec:
            self._last_metrics_at = now
            task = asyncio.create_task(self._publish_metrics(samples))
            self._background.add(task)
            task.add_done_callback(self._background.discard)
        return bad

    async def _publish_metrics(self, samples: list[dict[str, Any]]) -> None:
        """Store and broadcast one round of node telemetry."""
        for sample in samples:
            node_id = sample["node_id"]
            latency = sample["latency_ms"] if sample["reachable"] else 999.0
            jitter = 0.0
            if sample["reachable"]:
                previous = self._last_latency.get(node_id)
                jitter = round(abs(latency - previous), 3) if previous is not None else 0.0
                self._last_latency[node_id] = latency
            await self.metrics_collector.record_metric(
                node_id=node_id,
                latency_ms=latency,
                packet_loss_pct=sample["packet_loss_pct"],
                jitter_ms=jitter,
            )
            await self.event_bus.publish(
                METRIC_RECORDED, {**sample, "latency_ms": latency, "jitter_ms": jitter}
            )

    async def _raise_faults(self, graph: nx.Graph, confirmed: dict[str, Fault], now: float) -> None:
        """Diagnose newly confirmed faults, mark them down and raise one incident per root cause."""
        pending = dict(confirmed)
        while pending:
            diagnosis = self.diagnoser.diagnose(list(pending.values()), graph)
            root = diagnosis.root_cause_component
            if root not in pending:
                break

            # A failed device explains the failures of the links attached to it
            explained = {root}
            if graph.has_node(root):
                explained |= {
                    self.link_id(u, v)
                    for u, v in graph.edges
                    if root in (u, v) and self.link_id(u, v) in pending
                }
            for component in explained:
                pending.pop(component, None)
                self._faulty[component] = root

            detect_ms = (now - self._first_bad_at.get(root, now)) * 1000
            diagnosis.recommended_action = (
                f"{diagnosis.recommended_action} (confirmed after {self.confirmations} "
                f"consecutive failed probes, {detect_ms:.0f} ms after the first)"
            )
            node_status = (
                NodeStatus.DOWN
                if diagnosis.fault_type == FaultType.NODE_DOWN
                else NodeStatus.DEGRADED
            )
            await self._set_status(graph, explained, node_status, LinkStatus.DOWN)
            await self.alert_manager.create_alert(diagnosis)

    async def _recover(self, graph: nx.Graph, root: str, bad: dict[str, Fault]) -> None:
        """Restore a recovered root cause, fail routes back and close its incident."""
        members = {component for component, r in self._faulty.items() if r == root}
        for component in members:
            self._faulty.pop(component, None)
            self._streak[component] = 0
        healthy = {component for component in members if component not in bad}
        await self._set_status(graph, healthy, NodeStatus.UP, LinkStatus.UP)

        self.route_manager.rebuild_routes(graph)
        incident_id = self.alert_manager.incident_for(root)
        self.alert_manager.release_component(root)

        if incident_id:
            stamp = datetime.now(timezone.utc)
            note = f" Recovered at {stamp:%H:%M:%S} UTC; traffic returned to the primary routes."
            async with self.db.session_factory() as session:
                await session.execute(
                    update(Incident)
                    .where(Incident.id == incident_id)
                    .values(
                        resolved_at=func.coalesce(Incident.resolved_at, stamp),
                        resolution_notes=func.coalesce(Incident.resolution_notes, "") + note,
                    )
                )
                await session.commit()
        logger.info("HealthMonitor: '{}' recovered; routes rebuilt.", root)
        await self.event_bus.publish(TOPOLOGY_UPDATED, self._builder.get_topology_snapshot(graph))

    async def _set_status(
        self,
        graph: nx.Graph,
        components: set[str],
        node_status: NodeStatus,
        link_status: LinkStatus,
    ) -> None:
        """Write node and link status to the topology graph and the database."""
        node_ids = [c for c in components if graph.has_node(c)]
        links = [
            (u, v, data.get("id"))
            for u, v, data in graph.edges(data=True)
            if self.link_id(u, v) in components
        ]

        for node_id in node_ids:
            self._builder.update_node_status(graph, node_id, node_status)
        for u, v, _ in links:
            self._builder.update_link_status(graph, u, v, link_status)

        async with self.db.session_factory() as session:
            if node_ids:
                await session.execute(
                    update(Node).where(Node.id.in_(node_ids)).values(status=node_status)
                )
            config_ids = [link_id for _, _, link_id in links if link_id]
            if config_ids:
                await session.execute(
                    update(Link).where(Link.id.in_(config_ids)).values(status=link_status)
                )
            await session.commit()
        await self.event_bus.publish(TOPOLOGY_UPDATED, self._builder.get_topology_snapshot(graph))


__all__ = ["HealthMonitor"]
