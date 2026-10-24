"""Controlled network failure and degradation injection engine."""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone
from typing import Any

from src.core.events import (
    FAULT_DETECTED,
    EventBus,
)
from src.core.events import (
    event_bus as default_event_bus,
)
from src.core.models import (
    FaultType,
    Incident,
    IncidentStatus,
    LinkStatus,
    NodeStatus,
)
from src.simulation.virtual_network import VirtualNetwork
from src.utils.logger import logger


class FailureInjector:
    """Emulates real-world network outages and degradations within the simulation layer.

    Allows automated test suites, Chaos Engineering experiments, and demonstration
    workbenches to inject node drops, link cuts, high latency, and packet loss,
    broadcasting FAULT_DETECTED events to activate the self-healing subsystem.
    """

    def __init__(
        self,
        virtual_network: VirtualNetwork,
        event_bus: EventBus | None = None,
    ) -> None:
        """Initialize FailureInjector.

        Args:
            virtual_network: VirtualNetwork emulator to inject failures into.
            event_bus: Optional event bus to publish FAULT_DETECTED notifications.
        """
        self.virtual_network = virtual_network
        self.event_bus = event_bus or default_event_bus

        # When False, faults only change the simulated network and the HealthMonitor
        # has to detect them; when True, FAULT_DETECTED is announced immediately.
        self.announce_faults = True

        # History log of injected events: list of event dicts
        self._history: list[dict[str, Any]] = []

    async def inject_node_failure(self, node_id: str) -> None:
        """Simulate a total hardware crash or power loss of a network node.

        Marks the target node as DOWN and broadcasts a FAULT_DETECTED event.

        Args:
            node_id: Identifier of the node to fail (e.g. 'router-b').
        """
        logger.warning("Simulating NODE FAILURE on node: '{}'", node_id)
        self.virtual_network.set_node_status(node_id, NodeStatus.DOWN)

        incident = Incident(
            id=str(uuid.uuid4()),
            fault_type=FaultType.NODE_DOWN,
            affected_component=node_id,
            status=IncidentStatus.DETECTED,
            source_node=node_id,
            target_node=node_id,
            detected_at=datetime.now(timezone.utc),
            resolution_notes=f"Injected node failure on {node_id}",
        )

        record = {
            "action": "inject_node_failure",
            "target": node_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "incident_id": incident.id,
        }
        self._history.append(record)

        if self.event_bus and self.announce_faults:
            await self.event_bus.publish(
                FAULT_DETECTED,
                {
                    "incident": incident,
                    "fault_type": FaultType.NODE_DOWN.value,
                    "affected_component": node_id,
                    "node_id": node_id,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            )

        logger.info("Node failure on '{}' successfully injected.", node_id)

    async def inject_link_failure(self, source: str, target: str) -> None:
        """Simulate physical fiber cut or port down condition between two nodes.

        Marks the link as DOWN and broadcasts a FAULT_DETECTED event.

        Args:
            source: Source node identifier.
            target: Destination node identifier.
        """
        link_id = f"link-{source}-{target}"
        logger.warning(
            "Simulating LINK FAILURE on link: '{}' <-> '{}' ({})",
            source,
            target,
            link_id,
        )
        self.virtual_network.set_link_status(source, target, LinkStatus.DOWN)

        incident = Incident(
            id=str(uuid.uuid4()),
            fault_type=FaultType.LINK_DOWN,
            affected_component=link_id,
            status=IncidentStatus.DETECTED,
            source_node=source,
            target_node=target,
            detected_at=datetime.now(timezone.utc),
            resolution_notes=f"Injected link failure on {link_id}",
        )

        record = {
            "action": "inject_link_failure",
            "source": source,
            "target": target,
            "link_id": link_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "incident_id": incident.id,
        }
        self._history.append(record)

        if self.event_bus and self.announce_faults:
            await self.event_bus.publish(
                FAULT_DETECTED,
                {
                    "incident": incident,
                    "fault_type": FaultType.LINK_DOWN.value,
                    "affected_component": link_id,
                    "source": source,
                    "target": target,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            )

        logger.info("Link failure on '{}' <-> '{}' successfully injected.", source, target)

    async def inject_degradation(
        self,
        node_id: str,
        latency_ms: float = 500.0,
        loss_pct: float = 20.0,
    ) -> None:
        """Simulate buffer bloat, hardware throttling, or packet corruption.

        Args:
            node_id: Target node ID.
            latency_ms: Elevated RTT latency in milliseconds (default: 500ms).
            loss_pct: Packet loss percentage (default: 20%).
        """
        logger.warning(
            "Simulating DEGRADATION on node '{}': latency={}ms, packet_loss={}%",
            node_id,
            latency_ms,
            loss_pct,
        )
        self.virtual_network.inject_latency(node_id, latency_ms)
        self.virtual_network.inject_packet_loss(node_id, loss_pct)
        self.virtual_network.set_node_status(node_id, NodeStatus.DEGRADED)

        fault_type = (
            FaultType.HIGH_LATENCY if latency_ms > 200.0 else FaultType.PACKET_LOSS
        )
        incident = Incident(
            id=str(uuid.uuid4()),
            fault_type=fault_type,
            affected_component=node_id,
            status=IncidentStatus.DETECTED,
            source_node=node_id,
            target_node=node_id,
            detected_at=datetime.now(timezone.utc),
            resolution_notes=f"Injected degradation ({latency_ms}ms / {loss_pct}% loss) on {node_id}",
        )

        record = {
            "action": "inject_degradation",
            "node_id": node_id,
            "latency_ms": latency_ms,
            "loss_pct": loss_pct,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "incident_id": incident.id,
        }
        self._history.append(record)

        if self.event_bus and self.announce_faults:
            await self.event_bus.publish(
                FAULT_DETECTED,
                {
                    "incident": incident,
                    "fault_type": fault_type.value,
                    "affected_component": node_id,
                    "latency_ms": latency_ms,
                    "packet_loss_pct": loss_pct,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            )

        logger.info("Degradation injected on '{}'.", node_id)

    async def recover_node(self, node_id: str) -> None:
        """Restore a failed or degraded node back to fully operational UP status.

        Args:
            node_id: Target node identifier.
        """
        logger.info("Recovering node '{}' to healthy UP state...", node_id)
        self.virtual_network.set_node_status(node_id, NodeStatus.UP)
        self.virtual_network.inject_latency(
            node_id, VirtualNetwork.DEFAULT_NODE_LATENCY_MS
        )
        self.virtual_network.inject_packet_loss(node_id, 0.0)

        self._history.append(
            {
                "action": "recover_node",
                "node_id": node_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        )
        logger.info("Node '{}' has been recovered.", node_id)

    async def recover_link(self, source: str, target: str) -> None:
        """Restore a cut or degraded link back to UP status.

        Args:
            source: Source node identifier.
            target: Destination node identifier.
        """
        logger.info("Recovering link '{}' <-> '{}'...", source, target)
        self.virtual_network.set_link_status(source, target, LinkStatus.UP)

        self._history.append(
            {
                "action": "recover_link",
                "source": source,
                "target": target,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        )
        logger.info("Link '{}' <-> '{}' has been recovered.", source, target)

    async def run_scenario(self, scenario: dict[str, Any]) -> None:
        """Execute a structured sequence of timed failure and recovery actions.

        Scenario specification format:
        {
            "name": "core_link_sever_and_recovery",
            "description": "Severs core backbone link, pauses 5s, then recovers.",
            "steps": [
                {"action": "inject_link_failure", "source": "router-a", "target": "router-b"},
                {"action": "wait", "delay_sec": 3.0},
                {"action": "recover_link", "source": "router-a", "target": "router-b"}
            ]
        }

        Args:
            scenario: Dictionary defining scenario name and step list.
        """
        scenario_name = scenario.get("name", "Unnamed Scenario")
        steps = scenario.get("steps", [])

        logger.info(
            "Starting execution of simulation scenario '{}' ({} steps)...",
            scenario_name,
            len(steps),
        )

        for idx, step in enumerate(steps, start=1):
            action = step.get("action", "")
            logger.info("Scenario step {}/{}: action='{}'", idx, len(steps), action)

            if action == "inject_node_failure":
                await self.inject_node_failure(step["node_id"])

            elif action == "inject_link_failure":
                await self.inject_link_failure(step["source"], step["target"])

            elif action == "inject_degradation":
                await self.inject_degradation(
                    node_id=step["node_id"],
                    latency_ms=float(step.get("latency_ms", 500.0)),
                    loss_pct=float(step.get("loss_pct", 20.0)),
                )

            elif action == "recover_node":
                await self.recover_node(step["node_id"])

            elif action == "recover_link":
                await self.recover_link(step["source"], step["target"])

            elif action == "reset":
                self.virtual_network.reset()

            elif action == "wait":
                delay = float(step.get("delay_sec", step.get("duration_sec", 1.0)))
                logger.info("Scenario step {}: waiting {} seconds...", idx, delay)
                await asyncio.sleep(delay)

            else:
                logger.warning("Unknown scenario action: '{}'", action)

            # Optional step delay
            post_delay = float(step.get("post_delay_sec", 0.0))
            if post_delay > 0:
                await asyncio.sleep(post_delay)

        logger.info("Completed simulation scenario '{}'.", scenario_name)

    def get_history(self) -> list[dict[str, Any]]:
        """Return the complete chronological log of all failure injection events."""
        return list(self._history)


__all__ = ["FailureInjector"]
