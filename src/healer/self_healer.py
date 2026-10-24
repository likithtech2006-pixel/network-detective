"""Self-healing orchestrator coordinating automated route recovery and incident remediation."""

from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone
from typing import Any

import networkx as nx

from src.core.events import (
    FAULT_DETECTED,
    HEALING_COMPLETE,
    HEALING_STARTED,
    EventBus,
)
from src.core.events import (
    event_bus as default_event_bus,
)
from src.core.models import (
    ActionResult,
    ActionType,
    Database,
    FaultType,
    HealingAction,
    Incident,
    IncidentStatus,
)
from src.healer.path_finder import PathFinder
from src.healer.route_manager import RouteManager
from src.healer.traffic_redirector import TrafficRedirector
from src.utils.helpers import format_path
from src.utils.logger import logger


class SelfHealer:
    """Central remediation orchestrator for autonomous network recovery.

    Listens for FAULT_DETECTED events, evaluates affected communication flows,
    calculates alternate detour paths bypassing failed nodes or links, redirects
    traffic, records healing actions, and triggers rollback or escalation when necessary.
    """

    def __init__(
        self,
        path_finder: PathFinder | None = None,
        route_manager: RouteManager | None = None,
        traffic_redirector: TrafficRedirector | None = None,
        event_bus: EventBus | None = None,
        topology: nx.Graph | None = None,
        db: Database | None = None,
    ) -> None:
        """Initialize SelfHealer with required functional modules.

        Args:
            path_finder: Graph algorithm engine for computing detours.
            route_manager: Forwarding table state manager.
            traffic_redirector: Execution engine for route rerouting.
            event_bus: Publish-subscribe event bus instance.
            topology: Optional NetworkX topology graph.
            db: Optional Database session manager for persisting actions.
        """
        self.path_finder = path_finder or PathFinder()
        self.route_manager = route_manager or RouteManager()
        self.traffic_redirector = traffic_redirector or TrafficRedirector(
            self.route_manager, simulation_mode=True
        )
        self.event_bus = event_bus or default_event_bus
        self.topology = topology
        self.db = db

        # Turned off in Settings: faults are still detected but escalated, not rerouted
        self.enabled = True

        # Concurrency guard: track incident IDs currently undergoing healing
        self._active_healings: set[str] = set()
        self._lock = asyncio.Lock()

        # Subscribe to fault detection events
        self.event_bus.subscribe(FAULT_DETECTED, self.on_fault_detected)
        logger.info("SelfHealer subscribed to '{}' events.", FAULT_DETECTED)

    def get_topology(self) -> nx.Graph:
        """Retrieve the current topology graph, resolving from monitor singleton if needed.

        Returns:
            NetworkX graph representing network devices and links.
        """
        if self.topology is not None:
            return self.topology

        try:
            from src.monitor.topology_builder import get_topology

            return get_topology()
        except Exception as exc:
            logger.warning(
                "Could not load global topology via get_topology(): {}. Using empty graph.",
                exc,
            )
            return nx.Graph()

    async def on_fault_detected(self, data: Any) -> None:
        """Asynchronous event handler invoked when a network fault is detected.

        Unpacks incident payload and initiates autonomous healing.

        Args:
            data: Incident instance or dictionary containing incident attributes.
        """
        logger.info("SelfHealer received FAULT_DETECTED event: {}", data)
        try:
            incident = self._extract_incident(data)
            if incident:
                await self.heal(incident)
        except Exception as exc:
            logger.exception("Error during on_fault_detected execution: {}", exc)

    async def heal(self, incident: Incident) -> HealingAction:
        """Remediate a network incident by computing and applying an alternate route.

        Workflow:
        1. Guard against duplicate concurrent remediation for the same incident.
        2. Identify all affected routes that utilize the failed component.
        3. Exclude the broken component (node or link) from the topology graph.
        4. Calculate the optimal alternate path using PathFinder.
        5. If alternate path exists: redirect traffic, mark incident HEALING, return SUCCESS action.
        6. If no alternate path exists: mark incident ESCALATED, return FAILED action.
        7. Publish HEALING_COMPLETE event.

        Args:
            incident: The network incident to remediate.

        Returns:
            The recorded HealingAction instance.
        """
        async with self._lock:
            if incident.id in self._active_healings:
                logger.warning(
                    "Incident {} is already being healed; skipping duplicate attempt.",
                    incident.id,
                )
                # Return empty or placeholder action
                return HealingAction(
                    incident_id=incident.id,
                    action_type=ActionType.REROUTE,
                    result=ActionResult.FAILED,
                )
            self._active_healings.add(incident.id)

        try:
            logger.info(
                "Starting self-healing for incident {} (type={}, component={}, endpoints={} -> {})",
                incident.id,
                incident.fault_type,
                incident.affected_component,
                incident.source_node,
                incident.target_node,
            )

            # 1. Update status to HEALING and broadcast start
            incident.status = IncidentStatus.HEALING
            await self.event_bus.publish(
                HEALING_STARTED,
                {
                    "incident_id": incident.id,
                    "affected_component": incident.affected_component,
                    "fault_type": (
                        incident.fault_type.value
                        if hasattr(incident.fault_type, "value")
                        else str(incident.fault_type)
                    ),
                },
            )

            if not self.enabled:
                incident.status = IncidentStatus.ESCALATED
                incident.resolution_notes = (
                    "Self-healing is turned off in Settings, so no reroute was attempted; "
                    "an engineer has to fix this by hand."
                )
                healing_action = HealingAction(
                    incident_id=incident.id,
                    action_type=ActionType.ESCALATE,
                    old_route=incident.original_path,
                    new_route=None,
                    result=ActionResult.FAILED,
                    executed_at=datetime.now(timezone.utc),
                )
                await self._persist_healing(incident, healing_action)
                await self.event_bus.publish(
                    HEALING_COMPLETE,
                    {
                        "incident": incident,
                        "incident_id": incident.id,
                        "healing_action": healing_action,
                        "success": False,
                        "new_path": None,
                        "old_path": incident.original_path,
                    },
                )
                return healing_action

            topology = self.get_topology()
            component = incident.affected_component

            # 2. Identify affected routes
            affected_routes = self.route_manager.get_affected_routes(component)
            if not affected_routes:
                # Fallback to the incident's explicit source and target pair
                affected_routes = [(incident.source_node, incident.target_node)]

            logger.info(
                "Identified {} affected route(s) for component '{}': {}",
                len(affected_routes),
                component,
                affected_routes,
            )

            # 3. Determine exclusions for path finding
            excluded_nodes: list[str] = []
            excluded_edges: list[tuple[str, str]] = []

            is_node_fault = (
                incident.fault_type == FaultType.NODE_DOWN
                or (topology.has_node(component) and not component.startswith("link-"))
            )

            endpoints: tuple[str, str] | None = None
            if is_node_fault:
                excluded_nodes.append(component)
                element = component
            else:
                # It is a link failure or link degradation
                endpoints = self._resolve_link_endpoints(topology, component)
                if not endpoints and incident.source_node and incident.target_node:
                    endpoints = (incident.source_node, incident.target_node)
                if endpoints:
                    excluded_edges.append(endpoints)
                element = self.route_manager.link_key(*endpoints) if endpoints else component

            # Never detour through components that are already down from earlier faults
            for node_id, attrs in topology.nodes(data=True):
                if attrs.get("status") == "down" and node_id not in excluded_nodes:
                    excluded_nodes.append(node_id)
            for u, v, attrs in topology.edges(data=True):
                if attrs.get("status") == "down":
                    excluded_edges.append((u, v))

            # 4. Choose the primary flow and find its detour
            primary_src = incident.source_node
            primary_tgt = incident.target_node

            if endpoints:
                # A failed link's own traffic is the primary flow; flows crossing it move below
                primary_src, primary_tgt = endpoints
                incident.source_node, incident.target_node = endpoints
            elif is_node_fault and component in (primary_src, primary_tgt):
                # Traffic to or from a failed node cannot be rerouted, so heal the
                # first transit flow through it that still has a detour available.
                for src, tgt in affected_routes:
                    if component in (src, tgt):
                        continue
                    if self._detour(topology, src, tgt, element, excluded_nodes, excluded_edges)[0]:
                        primary_src, primary_tgt = src, tgt
                        incident.source_node, incident.target_node = src, tgt
                        break
            old_path = (
                self.route_manager.get_current_route(primary_src, primary_tgt)
                or incident.original_path
                or [primary_src, primary_tgt]
            )

            started = time.perf_counter()
            alternate_path, method = self._detour(
                topology, primary_src, primary_tgt, element, excluded_nodes, excluded_edges
            )
            compute_ms = (time.perf_counter() - started) * 1000

            # Also re-route any other affected flows registered in route_manager
            moved = 0
            for src, tgt in affected_routes:
                if (src, tgt) == (primary_src, primary_tgt):
                    continue
                flow_old = self.route_manager.get_current_route(src, tgt) or [src, tgt]
                flow_alt, _ = self._detour(
                    topology, src, tgt, element, excluded_nodes, excluded_edges
                )
                if flow_alt:
                    await self.traffic_redirector.redirect(
                        source=src,
                        target=tgt,
                        old_path=flow_old,
                        new_path=flow_alt,
                    )
                    moved += 1

            # 5. Evaluate outcome
            route_note: str | None = None
            if alternate_path:
                logger.info(
                    "Alternate route found for incident {} by {} in {:.3f} ms: [{}] (was [{}])",
                    incident.id,
                    method,
                    compute_ms,
                    format_path(alternate_path),
                    format_path(old_path),
                )

                # Execute traffic redirection for primary route
                redirect_res = await self.traffic_redirector.redirect(
                    source=primary_src,
                    target=primary_tgt,
                    old_path=old_path,
                    new_path=alternate_path,
                )

                if alternate_path == old_path:
                    route_note = "No active route used this component, so traffic was unaffected."
                else:
                    route_note = (
                        f"Detour from the {method} in {compute_ms:.3f} ms; "
                        f"{moved} other route(s) also moved."
                    )

                incident.original_path = old_path
                incident.alternate_path = alternate_path
                incident.status = IncidentStatus.HEALING

                healing_action = HealingAction(
                    incident_id=incident.id,
                    action_type=ActionType.REROUTE,
                    old_route=old_path,
                    new_route=alternate_path,
                    result=ActionResult.SUCCESS if redirect_res.success else ActionResult.FAILED,
                    executed_at=datetime.now(timezone.utc),
                )
            else:
                incident.status = IncidentStatus.ESCALATED
                incident.resolution_notes = self._escalation_reason(
                    topology,
                    component,
                    is_node_fault,
                    incident.fault_type == FaultType.NODE_DOWN,
                    excluded_nodes,
                    excluded_edges,
                )
                logger.error("Escalating incident {}: {}", incident.id, incident.resolution_notes)

                healing_action = HealingAction(
                    incident_id=incident.id,
                    action_type=ActionType.ESCALATE,
                    old_route=old_path,
                    new_route=None,
                    result=ActionResult.FAILED,
                    executed_at=datetime.now(timezone.utc),
                )

            # 6. Persist action if DB is configured
            await self._persist_healing(incident, healing_action)

            # 7. Publish HEALING_COMPLETE event
            is_success = healing_action.result == ActionResult.SUCCESS
            await self.event_bus.publish(
                HEALING_COMPLETE,
                {
                    "incident": incident,
                    "incident_id": incident.id,
                    "healing_action": healing_action,
                    "success": is_success,
                    "new_path": alternate_path,
                    "old_path": old_path,
                    "route_note": route_note,
                },
            )

            return healing_action

        finally:
            async with self._lock:
                self._active_healings.discard(incident.id)

    async def rollback(
        self, incident: Incident, healing_action: HealingAction
    ) -> HealingAction:
        """Rollback a previously applied healing action if verification fails.

        Restores the previous route in the routing table, records a rollback
        action, and updates incident state.

        Args:
            incident: Target network incident.
            healing_action: The failed or problematic healing action to revert.

        Returns:
            The recorded rollback HealingAction.
        """
        logger.warning(
            "Executing rollback for incident {} (action_id={})",
            incident.id,
            healing_action.id,
        )

        source = incident.source_node
        target = incident.target_node
        old_route = healing_action.old_route
        active_route = healing_action.new_route or []

        if old_route:
            # Revert routing table back to old_route
            await self.traffic_redirector.redirect(
                source=source,
                target=target,
                old_path=active_route,
                new_path=old_route,
            )
            self.route_manager.rollback_route(
                source=source,
                target=target,
                old_path=old_route,
                reason="healing_verification_failed",
            )

        rollback_action = HealingAction(
            incident_id=incident.id,
            action_type=ActionType.ROLLBACK,
            old_route=active_route,
            new_route=old_route,
            result=ActionResult.SUCCESS,
            executed_at=datetime.now(timezone.utc),
        )

        incident.status = IncidentStatus.ESCALATED
        incident.resolution_notes = "Healing failed verification; route rolled back and escalated."

        await self._persist_healing(incident, rollback_action)
        return rollback_action

    def _detour(
        self,
        topology: nx.Graph,
        source: str,
        target: str,
        element: str,
        excluded_nodes: list[str],
        excluded_edges: list[tuple[str, str]],
    ) -> tuple[list[str] | None, str]:
        """Find a path that avoids every excluded element, preferring the pre-computed backup.

        Args:
            topology: Current topology graph.
            source: Flow source node.
            target: Flow destination node.
            element: Failed element key (node ID or RouteManager.link_key).
            excluded_nodes: Nodes the path must not use.
            excluded_edges: Links the path must not use.

        Returns:
            (path or None, how it was found: "pre-computed backup" or "Dijkstra").
        """
        backup = self.route_manager.get_backup_route(source, target, element)
        if backup and self._avoids(backup, excluded_nodes, excluded_edges):
            return backup, "pre-computed backup"
        path = self.path_finder.find_shortest_path(
            graph=topology,
            source=source,
            target=target,
            excluded_edges=excluded_edges,
            excluded_nodes=excluded_nodes,
        )
        return path, "Dijkstra"

    @staticmethod
    def _avoids(
        path: list[str], excluded_nodes: list[str], excluded_edges: list[tuple[str, str]]
    ) -> bool:
        """True when a path uses none of the excluded nodes or links."""
        if any(node in excluded_nodes for node in path):
            return False
        blocked = {frozenset(edge) for edge in excluded_edges}
        hops = zip(path[:-1], path[1:], strict=True)
        return not any(frozenset(hop) in blocked for hop in hops)

    @staticmethod
    def _escalation_reason(
        topology: nx.Graph,
        component: str,
        is_node_fault: bool,
        is_down: bool,
        excluded_nodes: list[str],
        excluded_edges: list[tuple[str, str]],
    ) -> str:
        """Explain to an engineer why no detour exists and what is cut off."""
        state, fix = ("down", "repair or restart") if is_down else ("degraded", "investigate")
        def core(nodes: list[str], edges: list[tuple[str, str]]) -> set[str]:
            """Largest connected group of devices once the given elements are removed."""
            view = nx.restricted_view(topology, nodes, edges + [(v, u) for u, v in edges])
            islands = list(nx.connected_components(view))
            return max(islands, key=len) if islands else set()

        # Only devices that THIS failure disconnects from the rest, not earlier ones
        if is_node_fault:
            before = core(
                [n for n in excluded_nodes if n != component],
                [e for e in excluded_edges if component not in e],
            )
        else:
            failed_link = set(excluded_edges[0]) if excluded_edges else set()
            before = core(excluded_nodes, [e for e in excluded_edges if set(e) != failed_link])
        after = core(excluded_nodes, excluded_edges)
        stranded = sorted(before - after - {component})
        cut_off = ", ".join(stranded)

        if is_node_fault and stranded:
            return (
                f"Device '{component}' is {state} and cuts off {cut_off}; no other path "
                f"reaches it. {fix.capitalize()} '{component}'."
            )
        if is_node_fault:
            return (
                f"Device '{component}' is {state}. No other traffic passes through it, so there "
                f"is nothing to reroute; {fix} the device."
            )
        if stranded:
            return (
                f"Link '{component}' was the only connection to {cut_off}, which stays "
                f"unreachable until the link is repaired."
            )
        return f"No path avoids the failed components around '{component}'."

    def _resolve_link_endpoints(
        self, graph: nx.Graph, component: str
    ) -> tuple[str, str] | None:
        """Identify (u, v) edge endpoints corresponding to a link component string.

        Args:
            graph: Topology graph.
            component: Link ID or name.

        Returns:
            Tuple of node IDs (u, v), or None.
        """
        for u, v, data in graph.edges(data=True):
            if data.get("id") == component:
                return (str(u), str(v))

        cleaned = component
        if cleaned.startswith("link-"):
            cleaned = cleaned[5:]

        nodes = list(graph.nodes)
        for u in nodes:
            prefix = f"{u}-"
            if cleaned.startswith(prefix):
                v = cleaned[len(prefix) :]
                if v in graph:
                    return (u, v)

        return None

    def _extract_incident(self, data: Any) -> Incident | None:
        """Parse raw event payload into an Incident model instance.

        Args:
            data: Raw event object or dict.

        Returns:
            Incident model or None.
        """
        if isinstance(data, Incident):
            return data

        if isinstance(data, dict):
            if "incident" in data and isinstance(data["incident"], Incident):
                return data["incident"]

            # Construct Incident from dictionary fields
            fault_type_val = data.get("fault_type", FaultType.LINK_DOWN)
            if isinstance(fault_type_val, str):
                try:
                    fault_type = FaultType(fault_type_val)
                except ValueError:
                    fault_type = FaultType.LINK_DOWN
            else:
                fault_type = fault_type_val

            return Incident(
                id=data.get("id", data.get("incident_id")),
                fault_type=fault_type,
                affected_component=data.get(
                    "affected_component", data.get("component", "unknown")
                ),
                status=IncidentStatus.DETECTED,
                source_node=data.get("source_node", data.get("source", "")),
                target_node=data.get("target_node", data.get("target", "")),
                original_path=data.get("original_path"),
            )

        return None

    async def _persist_healing(
        self, incident: Incident, action: HealingAction
    ) -> None:
        """Persist incident status updates and healing action to the database if available.

        Args:
            incident: Incident model.
            action: HealingAction model.
        """
        if self.db is None:
            return

        try:
            async with self.db.session_factory() as session:
                session.add(action)
                # Merge updated incident
                await session.merge(incident)
                await session.commit()
                logger.debug(
                    "Persisted healing action {} for incident {}",
                    action.id,
                    incident.id,
                )
        except Exception as exc:
            logger.warning("Could not persist healing action to DB: {}", exc)


__all__ = ["SelfHealer"]
