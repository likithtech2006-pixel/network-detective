"""In-memory network routing table and route history manager."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

import networkx as nx

from src.utils.logger import logger


class RouteManager:
    """Manages active network routes, history tracking, and failure route impact analysis.

    Maintains the canonical forwarding table mapping (source, target) pairs to
    active hops, records all historical routing changes, and detects which active
    routes traverse a failed node or link.
    """

    def __init__(
        self,
        initial_routes: dict[tuple[str, str], list[str]] | None = None,
    ) -> None:
        """Initialize RouteManager with an optional set of pre-computed routes.

        Args:
            initial_routes: Optional dictionary mapping (source, target) to list of hops.
        """
        # Active routing table: (source, target) -> [node_1, node_2, ..., node_n]
        self._routing_table: dict[tuple[str, str], list[str]] = {}

        # Fast-reroute table: (source, target, failed element) -> pre-computed detour
        self._backup_routes: dict[tuple[str, str, str], list[str]] = {}

        # History tracking: (source, target) -> list of record dicts
        self._history: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)

        if initial_routes:
            for (src, tgt), path in initial_routes.items():
                self.apply_route(src, tgt, path, reason="initial_seeding")

    def get_current_route(self, source: str, target: str) -> list[str] | None:
        """Retrieve the active route path for a given source and target pair.

        Args:
            source: Source node identifier.
            target: Destination node identifier.

        Returns:
            List of node IDs in the route, or None if no route is registered.
        """
        path = self._routing_table.get((source, target))
        return list(path) if path is not None else None

    def apply_route(
        self,
        source: str,
        target: str,
        new_path: list[str],
        reason: str = "reroute",
    ) -> None:
        """Update the routing table with a newly computed path and record history.

        Args:
            source: Source node identifier.
            target: Destination node identifier.
            new_path: New ordered sequence of node IDs.
            reason: Context description for the routing change.
        """
        if not new_path or new_path[0] != source or new_path[-1] != target:
            logger.warning(
                "Applying route with mismatched endpoints: ({}, {}) vs path {}",
                source,
                target,
                new_path,
            )

        old_path = self.get_current_route(source, target)

        # Record history event
        history_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "source": source,
            "target": target,
            "old_path": old_path,
            "new_path": list(new_path),
            "reason": reason,
        }
        self._history[(source, target)].append(history_entry)

        # Update active routing table
        self._routing_table[(source, target)] = list(new_path)

        logger.info(
            "Route updated: ({} -> {}) | Old: {} | New: {} | Reason: {}",
            source,
            target,
            " -> ".join(old_path) if old_path else "None",
            " -> ".join(new_path),
            reason,
        )

    def rollback_route(
        self,
        source: str,
        target: str,
        old_path: list[str],
        reason: str = "rollback",
    ) -> None:
        """Restore a previous route for a given source and target pair.

        Args:
            source: Source node identifier.
            target: Destination node identifier.
            old_path: The previous route path to restore.
            reason: Context description for the rollback.
        """
        current_path = self.get_current_route(source, target)

        history_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "source": source,
            "target": target,
            "old_path": current_path,
            "new_path": list(old_path),
            "reason": reason,
        }
        self._history[(source, target)].append(history_entry)

        self._routing_table[(source, target)] = list(old_path)

        logger.warning(
            "Route rollback executed: ({} -> {}) | Restored: {} | Replaced: {} | Reason: {}",
            source,
            target,
            " -> ".join(old_path),
            " -> ".join(current_path) if current_path else "None",
            reason,
        )

    def get_all_routes(self) -> dict[tuple[str, str], list[str]]:
        """Return a copy of the entire active routing table.

        Returns:
            Dictionary mapping (source, target) tuples to active path lists.
        """
        return {key: list(path) for key, path in self._routing_table.items()}

    def get_affected_routes(self, component: str) -> list[tuple[str, str]]:
        """Identify all active routes that traverse a failed node or link component.

        Args:
            component: Failed component name (node ID or link ID like 'link-a-b').

        Returns:
            List of (source, target) pairs whose active route passes through the component.
        """
        if not component:
            return []

        affected: list[tuple[str, str]] = []

        # Check if component represents a link: extract potential endpoints
        endpoints = self._parse_link_component(component)

        for (src, tgt), path in self._routing_table.items():
            # If component is a node:
            if component in path:
                affected.append((src, tgt))
                continue

            # If component is a link:
            if endpoints:
                u, v = endpoints
                for step_u, step_v in zip(path[:-1], path[1:]):
                    if (step_u == u and step_v == v) or (step_u == v and step_v == u):
                        affected.append((src, tgt))
                        break

        return affected

    def get_route_history(
        self, source: str, target: str
    ) -> list[dict[str, Any]]:
        """Retrieve the complete chronological history of routing changes for a pair.

        Args:
            source: Source node identifier.
            target: Destination node identifier.

        Returns:
            List of history entries with timestamp, old_path, new_path, and reason.
        """
        return list(self._history.get((source, target), []))

    def set_initial_routes_from_graph(self, graph: nx.Graph) -> None:
        """Seed all-pairs shortest paths from a NetworkX graph into the routing table.

        Args:
            graph: Topology graph with edge weights.
        """
        nodes = list(graph.nodes)
        count = 0
        for src in nodes:
            for tgt in nodes:
                if src != tgt:
                    try:
                        path = nx.dijkstra_path(
                            graph, source=src, target=tgt, weight="weight"
                        )
                        self.apply_route(src, tgt, path, reason="topology_init")
                        count += 1
                    except (nx.NetworkXNoPath, nx.NodeNotFound):
                        continue

        logger.info("Initialized routing table with {} routes from graph.", count)

    def rebuild_routes(self, graph: nx.Graph) -> None:
        """Discard the active routing table and recompute shortest paths over healthy elements.

        Nodes and links whose 'status' attribute is 'down' are skipped, so the
        rebuilt table only contains routes that are currently usable.

        Args:
            graph: Topology graph with edge weights and status attributes.
        """
        healthy = nx.subgraph_view(
            graph,
            filter_node=lambda n: graph.nodes[n].get("status") != "down",
            filter_edge=lambda u, v: graph[u][v].get("status") != "down",
        )
        self._routing_table.clear()
        self.set_initial_routes_from_graph(healthy)
        self._precompute_backups(healthy)

    @staticmethod
    def link_key(u: str, v: str) -> str:
        """Direction-independent key for a link, used to index backup routes."""
        a, b = sorted((u, v))
        return f"{a}|{b}"

    def _precompute_backups(self, graph: nx.Graph) -> None:
        """Store, for every route and every link or transit device on it, the best detour avoiding it.

        This mirrors fast-reroute in production routers: the detour is ready before
        anything fails, so healing is a table lookup instead of a fresh Dijkstra run.

        Args:
            graph: Healthy topology the current routes were computed on.
        """
        self._backup_routes.clear()
        for (src, tgt), path in self._routing_table.items():
            for u, v in zip(path[:-1], path[1:], strict=True):
                view = nx.restricted_view(graph, [], [(u, v), (v, u)])
                self._store_backup(view, src, tgt, self.link_key(u, v))
            for node in path[1:-1]:
                view = nx.restricted_view(graph, [node], [])
                self._store_backup(view, src, tgt, node)
        logger.info("Pre-computed {} backup routes.", len(self._backup_routes))

    def _store_backup(self, view: nx.Graph, src: str, tgt: str, element: str) -> None:
        """Record the shortest path in a view that already excludes one element."""
        try:
            self._backup_routes[(src, tgt, element)] = nx.dijkstra_path(
                view, source=src, target=tgt, weight="weight"
            )
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            pass

    def get_backup_route(self, source: str, target: str, element: str) -> list[str] | None:
        """Return the pre-computed detour for a flow when one element fails.

        Args:
            source: Flow source node.
            target: Flow destination node.
            element: Failed node ID, or a link key from link_key().

        Returns:
            Backup path, or None if no detour was computed for that failure.
        """
        return self._backup_routes.get((source, target, element))

    def _parse_link_component(self, link_component: str) -> tuple[str, str] | None:
        """Helper to extract endpoints from a link string like 'link-a-b' or 'a-b'.

        Args:
            link_component: String identifier of the link.

        Returns:
            (u, v) tuple or None.
        """
        cleaned = link_component
        if cleaned.startswith("link-"):
            cleaned = cleaned[5:]

        # Split on hyphen
        parts = cleaned.split("-")
        if len(parts) == 2:
            return (parts[0], parts[1])
        elif len(parts) > 2:
            # Handle multi-part node names like router-a-switch-c
            # Find matching nodes from current routes
            all_known_nodes = set()
            for path in self._routing_table.values():
                all_known_nodes.update(path)

            for u in all_known_nodes:
                prefix = f"{u}-"
                if cleaned.startswith(prefix):
                    v = cleaned[len(prefix) :]
                    if v in all_known_nodes:
                        return (u, v)

        return None


__all__ = ["RouteManager"]
