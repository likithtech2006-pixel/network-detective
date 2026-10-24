"""Path computation and graph analysis algorithms for self-healing network routing."""

from __future__ import annotations

import networkx as nx

from src.utils.logger import logger


class PathFinder:
    """Network path computation engine utilizing NetworkX graph algorithms.

    Computes optimal shortest paths, k-alternate paths, path costs, and
    identifies routes impacted by failed network components.
    """

    def __init__(self) -> None:
        """Initialize PathFinder."""
        pass

    def find_shortest_path(
        self,
        graph: nx.Graph,
        source: str,
        target: str,
        excluded_edges: list[tuple[str, str]] | None = None,
        excluded_nodes: list[str] | None = None,
    ) -> list[str] | None:
        """Compute the shortest path between source and target avoiding excluded elements.

        Creates an isolated subgraph copy with specified excluded nodes and edges
        removed, then calculates the Dijkstra shortest path based on edge weights.

        Args:
            graph: Base NetworkX topology graph.
            source: Source node identifier.
            target: Destination node identifier.
            excluded_edges: List of (u, v) edge tuples to exclude from routing.
            excluded_nodes: List of node IDs to exclude from routing.

        Returns:
            List of node IDs representing the ordered path, or None if no path exists.
        """
        if not graph or source not in graph or target not in graph:
            return None

        # If source or target is explicitly excluded, no path can exist
        excluded_nodes_set = set(excluded_nodes or [])
        if source in excluded_nodes_set or target in excluded_nodes_set:
            return None

        subgraph = graph.copy()

        # Remove excluded nodes
        for node in excluded_nodes_set:
            if subgraph.has_node(node):
                subgraph.remove_node(node)

        # Remove excluded edges (handling bidirectional links)
        if excluded_edges:
            for edge in excluded_edges:
                if len(edge) >= 2:
                    u, v = edge[0], edge[1]
                    if subgraph.has_edge(u, v):
                        subgraph.remove_edge(u, v)
                    if subgraph.has_edge(v, u):
                        subgraph.remove_edge(v, u)

        # Ensure both endpoints remain present and connected in subgraph
        if source not in subgraph or target not in subgraph:
            return None

        try:
            path: list[str] = nx.dijkstra_path(
                subgraph,
                source=source,
                target=target,
                weight="weight",
            )
            logger.debug(
                "Shortest path found {} -> {}: {} (cost={})",
                source,
                target,
                " -> ".join(path),
                self.compute_path_cost(subgraph, path),
            )
            return path
        except (nx.NetworkXNoPath, nx.NodeNotFound, nx.NetworkXError) as exc:
            logger.debug("No path found between {} and {}: {}", source, target, exc)
            return None

    def find_k_shortest_paths(
        self,
        graph: nx.Graph,
        source: str,
        target: str,
        k: int = 3,
        excluded_edges: list[tuple[str, str]] | None = None,
        excluded_nodes: list[str] | None = None,
    ) -> list[list[str]]:
        """Find up to k shortest alternative paths between source and target.

        Uses Yen's algorithm / nx.shortest_simple_paths to generate loopless paths
        sorted in ascending order of total cumulative edge weight.

        Args:
            graph: Base NetworkX topology graph.
            source: Source node identifier.
            target: Destination node identifier.
            k: Maximum number of alternative paths to return (default: 3).
            excluded_edges: Optional list of (u, v) edges to exclude.
            excluded_nodes: Optional list of node IDs to exclude.

        Returns:
            List of up to k distinct paths, each represented as a list of node IDs.
        """
        if not graph or source not in graph or target not in graph or k <= 0:
            return []

        excluded_nodes_set = set(excluded_nodes or [])
        if source in excluded_nodes_set or target in excluded_nodes_set:
            return []

        subgraph = graph.copy()

        for node in excluded_nodes_set:
            if subgraph.has_node(node):
                subgraph.remove_node(node)

        if excluded_edges:
            for edge in excluded_edges:
                if len(edge) >= 2:
                    u, v = edge[0], edge[1]
                    if subgraph.has_edge(u, v):
                        subgraph.remove_edge(u, v)
                    if subgraph.has_edge(v, u):
                        subgraph.remove_edge(v, u)

        if source not in subgraph or target not in subgraph:
            return []

        paths: list[list[str]] = []
        try:
            generator = nx.shortest_simple_paths(
                subgraph,
                source=source,
                target=target,
                weight="weight",
            )
            for path in generator:
                paths.append(path)
                if len(paths) >= k:
                    break
        except (nx.NetworkXNoPath, nx.NodeNotFound, nx.NetworkXError):
            pass

        # Ensure paths are strictly sorted by cost
        paths.sort(key=lambda p: self.compute_path_cost(subgraph, p))
        return paths

    def compute_path_cost(self, graph: nx.Graph, path: list[str]) -> float:
        """Calculate the total metric cost/weight along an ordered sequence of nodes.

        Sums the 'weight' attribute on each traversed edge in the path.

        Args:
            graph: NetworkX graph containing the edge attributes.
            path: List of sequential node identifiers.

        Returns:
            Sum of edge weights along the path, or 0.0 if invalid/single-node path.
        """
        if not graph or not path or len(path) < 2:
            return 0.0

        total_cost = 0.0
        for u, v in zip(path[:-1], path[1:]):
            if graph.has_edge(u, v):
                edge_data = graph.get_edge_data(u, v, default={})
                total_cost += float(edge_data.get("weight", 1.0))
            else:
                return float("inf")

        return round(total_cost, 4)

    def get_all_paths_through_component(
        self,
        graph: nx.Graph,
        component: str,
        cutoff: int = 6,
    ) -> list[list[str]]:
        """Identify all simple network paths that traverse a specified component.

        Supports components specified either as node identifiers or link identifiers
        (e.g., 'link-router-a-router-b' or 'router-a-router-b').

        Args:
            graph: Base NetworkX topology graph.
            component: Failed node ID or link ID.
            cutoff: Maximum hop depth limit to prevent combinatorial explosion.

        Returns:
            List of distinct paths that pass through the failed component.
        """
        if not graph or not component:
            return []

        paths_found: list[list[str]] = []

        # Case 1: Component is a node in the graph
        if graph.has_node(component):
            nodes = list(graph.nodes)
            for i, src in enumerate(nodes):
                if src == component:
                    continue
                for tgt in nodes[i + 1 :]:
                    if tgt == component:
                        continue
                    try:
                        for path in nx.all_simple_paths(
                            graph, source=src, target=tgt, cutoff=cutoff
                        ):
                            if component in path:
                                paths_found.append(path)
                    except (nx.NetworkXNoPath, nx.NodeNotFound):
                        continue
            return paths_found

        # Case 2: Component is a link identifier
        endpoints = self._parse_link_endpoints(graph, component)
        if endpoints:
            u, v = endpoints
            nodes = list(graph.nodes)
            for i, src in enumerate(nodes):
                for tgt in nodes[i + 1 :]:
                    try:
                        for path in nx.all_simple_paths(
                            graph, source=src, target=tgt, cutoff=cutoff
                        ):
                            # Check if edge (u, v) or (v, u) is traversed consecutively
                            for step_u, step_v in zip(path[:-1], path[1:]):
                                if (step_u == u and step_v == v) or (
                                    step_u == v and step_v == u
                                ):
                                    paths_found.append(path)
                                    break
                    except (nx.NetworkXNoPath, nx.NodeNotFound):
                        continue

        return paths_found

    def _parse_link_endpoints(
        self, graph: nx.Graph, link_component: str
    ) -> tuple[str, str] | None:
        """Resolve source and target node IDs from a link component string.

        Args:
            graph: NetworkX graph with edge metadata.
            link_component: String identifier for the link.

        Returns:
            Tuple of (u, v) node IDs, or None if unmatched.
        """
        # 1. Search existing edge attributes for matching link id
        for u, v, data in graph.edges(data=True):
            if data.get("id") == link_component:
                return (str(u), str(v))

        # 2. Match standard naming convention "link-{src}-{tgt}"
        cleaned = link_component
        if cleaned.startswith("link-"):
            cleaned = cleaned[5:]

        # Check all node combinations
        nodes = list(graph.nodes)
        for u in nodes:
            prefix = f"{u}-"
            if cleaned.startswith(prefix):
                v = cleaned[len(prefix) :]
                if v in graph:
                    return (u, v)

        return None


__all__ = ["PathFinder"]
