"""Diagnostic root cause analysis and affected path identification using graph traversal."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

import networkx as nx

from src.core.models import ActionType, FaultType
from src.detector.fault_classifier import FAULT_PRIORITY, Fault
from src.utils.logger import logger


@dataclass
class DiagnosisResult:
    """Outcome of root cause analysis identifying the faulty component and affected routes."""

    root_cause_component: str
    fault_type: FaultType
    affected_paths: list[list[str]] = field(default_factory=list)
    recommended_action: str = ""
    action_type: ActionType = ActionType.REROUTE
    confidence: float = 0.90
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert dataclass fields to a standard dictionary."""
        d = asdict(self)
        d["fault_type"] = self.fault_type.value
        d["action_type"] = self.action_type.value
        return d


class Diagnoser:
    """Performs topological root cause analysis across correlated network faults."""

    def __init__(self) -> None:
        """Initialize Diagnoser."""
        pass

    def diagnose(
        self,
        faults: list[Fault],
        topology: nx.Graph,
    ) -> DiagnosisResult:
        """Analyze classified faults against the network topology to isolate root cause.

        Finds common upstream devices, computes affected communication routes,
        and determines appropriate self-healing remediation.

        Args:
            faults: Ranked list of classified faults from FaultClassifier.
            topology: Live NetworkX topology graph.

        Returns:
            DiagnosisResult with root cause, affected paths, and recommended action.
        """
        if not faults:
            return DiagnosisResult(
                root_cause_component="",
                fault_type=FaultType.NODE_DOWN,
                affected_paths=[],
                recommended_action="No active faults detected; network is healthy",
                action_type=ActionType.REROUTE,
                confidence=1.0,
            )

        # 1. Identify Root Cause Component
        root_cause_fault = self._identify_root_cause(faults, topology)
        root_comp = root_cause_fault.affected_component
        fault_type = root_cause_fault.fault_type

        # 2. Find All Affected Paths in the Graph
        affected_paths = self._find_affected_paths(root_comp, topology)

        # 3. Determine Recommended Action and Verification Feasibility
        action_type, recommendation = self._determine_action(
            root_comp=root_comp,
            fault_type=fault_type,
            affected_paths=affected_paths,
            topology=topology,
        )

        logger.info(
            "Diagnosis complete: root_cause='{}' ({}), affected_paths={}, recommendation='{}'",
            root_comp,
            fault_type.value,
            len(affected_paths),
            recommendation,
        )

        return DiagnosisResult(
            root_cause_component=root_comp,
            fault_type=fault_type,
            affected_paths=affected_paths,
            recommended_action=recommendation,
            action_type=action_type,
            confidence=root_cause_fault.confidence,
            details={
                "all_fault_count": len(faults),
                "severity": root_cause_fault.severity,
                "fault_details": root_cause_fault.details,
            },
        )

    def _identify_root_cause(
        self,
        faults: list[Fault],
        topology: nx.Graph,
    ) -> Fault:
        """Select the true root-cause fault by analyzing topology hierarchy and fault types.

        If multiple downstream servers show symptoms, an upstream router or switch is the root.
        """
        if len(faults) == 1:
            return faults[0]

        # Prioritize NODE_DOWN or LINK_DOWN over degradation
        critical_faults = [f for f in faults if f.severity == "critical"]
        candidates = critical_faults if critical_faults else faults

        # Check for upstream devices in candidate faults
        # Routers > Switches > Servers
        hierarchy = {"router": 3, "switch": 2, "server": 1}

        def _node_rank(comp_id: str) -> int:
            if topology.has_node(comp_id):
                node_type = str(topology.nodes[comp_id].get("type", "router")).lower()
                return hierarchy.get(node_type, 1)
            # If link, rank based on its endpoints
            return 2

        # Sort by: FaultType priority first, then architectural hierarchy rank, then confidence
        ranked_candidates = sorted(
            candidates,
            key=lambda f: (
                FAULT_PRIORITY.get(f.fault_type, 99),
                -_node_rank(f.affected_component),
                -f.confidence,
            ),
        )

        # Check if multiple nodes are faulty and share a common upstream neighbor
        faulty_nodes = [f.affected_component for f in faults if topology.has_node(f.affected_component)]
        if len(faulty_nodes) > 1:
            # Find common neighbors
            common_neighbors = None
            for fn in faulty_nodes:
                neighbors = set(topology.neighbors(fn))
                if common_neighbors is None:
                    common_neighbors = neighbors
                else:
                    common_neighbors = common_neighbors.intersection(neighbors)

            if common_neighbors:
                for cand in ranked_candidates:
                    if cand.affected_component in common_neighbors:
                        return cand

        return ranked_candidates[0]

    def _find_affected_paths(
        self,
        root_component: str,
        topology: nx.Graph,
    ) -> list[list[str]]:
        """Identify all shortest paths in the topology that traverse the failed component.

        Args:
            root_component: Failed node ID or link ID (e.g. 'router-b' or 'link-a-b').
            topology: NetworkX topology graph.

        Returns:
            List of affected paths represented as node ID sequences.
        """
        affected_paths: list[list[str]] = []
        is_node = topology.has_node(root_component)

        # Parse link endpoints if component is a link
        link_endpoints: tuple[str, str] | None = None
        if not is_node:
            for u, v, attrs in topology.edges(data=True):
                if attrs.get("id") == root_component or f"link-{u}-{v}" == root_component or f"link-{v}-{u}" == root_component:
                    link_endpoints = (u, v)
                    break

        nodes = list(topology.nodes)
        for i in range(len(nodes)):
            for j in range(i + 1, len(nodes)):
                src, tgt = nodes[i], nodes[j]
                try:
                    if nx.has_path(topology, src, tgt):
                        path = nx.shortest_path(topology, source=src, target=tgt, weight="weight")
                        # Check if path is affected
                        if is_node and root_component in path:
                            affected_paths.append(path)
                        elif link_endpoints:
                            u, v = link_endpoints
                            # Check if edge (u,v) or (v,u) is traversed in path
                            for step_idx in range(len(path) - 1):
                                step = (path[step_idx], path[step_idx + 1])
                                if step == (u, v) or step == (v, u):
                                    affected_paths.append(path)
                                    break
                except (nx.NetworkXNoPath, nx.NodeNotFound):
                    continue

        return affected_paths

    def _determine_action(
        self,
        root_comp: str,
        fault_type: FaultType,
        affected_paths: list[list[str]],
        topology: nx.Graph,
    ) -> tuple[ActionType, str]:
        """Determine appropriate remediation action based on network redundancy.

        Returns:
            Tuple of (ActionType, recommendation_string).
        """
        if not affected_paths:
            if fault_type == FaultType.NODE_DOWN:
                return (
                    ActionType.ESCALATE,
                    f"Escalate to NOC: Node {root_comp} is down but no transit paths are active",
                )
            return (
                ActionType.REROUTE,
                f"Inspect and remediate {fault_type.value} on {root_comp}",
            )

        # Check if alternative paths exist for affected node pairs when removing root_comp
        subgraph = topology.copy()
        if subgraph.has_node(root_comp):
            subgraph.remove_node(root_comp)

        has_alternatives = False
        for path in affected_paths:
            src, tgt = path[0], path[-1]
            if src != root_comp and tgt != root_comp:
                if subgraph.has_node(src) and subgraph.has_node(tgt) and nx.has_path(subgraph, src, tgt):
                    has_alternatives = True
                    break

        if fault_type in (FaultType.NODE_DOWN, FaultType.LINK_DOWN):
            if has_alternatives:
                return (
                    ActionType.REROUTE,
                    f"Reroute affected traffic around failed component '{root_comp}' via healthy alternate path",
                )
            return (
                ActionType.ESCALATE,
                f"Escalate to NOC: Critical outage on '{root_comp}' with no redundant bypass paths available",
            )
        elif fault_type in (FaultType.HIGH_LATENCY, FaultType.PACKET_LOSS, FaultType.LINK_DEGRADED):
            if has_alternatives:
                return (
                    ActionType.REROUTE,
                    f"Dynamically divert traffic from degraded component '{root_comp}' to secondary low-latency route",
                )
            return (
                ActionType.ESCALATE,
                f"Escalate to NOC: High latency/loss observed on '{root_comp}' but no alternate path available",
            )

        return (
            ActionType.REROUTE,
            f"Remediate {fault_type.value} on {root_comp}",
        )
