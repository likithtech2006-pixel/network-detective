"""NetworkX-based topology graph builder, updater, and serializer."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import networkx as nx

from src.core.config import NetworkConfig, Settings, get_settings
from src.core.models import LinkStatus, NodeStatus
from src.utils.logger import logger

# Module-level singleton topology graph
_current_topology: nx.Graph | None = None


class TopologyBuilder:
    """Constructs and manages NetworkX graph representations of network infrastructure."""

    def __init__(self) -> None:
        """Initialize TopologyBuilder."""
        pass

    def build_from_config(
        self,
        config: Settings | NetworkConfig | dict[str, Any] | None = None,
    ) -> nx.Graph:
        """Create a NetworkX graph with node and edge attributes parsed from configuration.

        Args:
            config: Settings, NetworkConfig, raw dictionary, or None (loads from get_settings()).

        Returns:
            Configured nx.Graph instance.
        """
        global _current_topology
        graph = nx.Graph()

        # Resolve nodes and links from different input formats
        nodes_data: list[Any] = []
        links_data: list[Any] = []

        if config is None:
            settings = get_settings()
            nodes_data = settings.network.nodes
            links_data = settings.network.links
        elif isinstance(config, Settings):
            nodes_data = config.network.nodes
            links_data = config.network.links
        elif isinstance(config, NetworkConfig):
            nodes_data = config.nodes
            links_data = config.links
        elif isinstance(config, dict):
            nodes_data = config.get("nodes", [])
            links_data = config.get("links", [])

        # 1. Populate Nodes
        for item in nodes_data:
            if hasattr(item, "id"):
                node_id = item.id
                name = getattr(item, "name", node_id)
                ip = getattr(item, "ip_address", "")
                node_type = getattr(item, "node_type", "router")
                desc = getattr(item, "description", "")
            elif isinstance(item, dict):
                node_id = str(item.get("id"))
                name = item.get("name", node_id)
                ip = item.get("ip_address", item.get("ip", ""))
                node_type = item.get("node_type", item.get("type", "router"))
                desc = item.get("description", "")
            else:
                continue

            graph.add_node(
                node_id,
                id=node_id,
                name=name,
                ip=ip,
                ip_address=ip,
                type=node_type,
                node_type=node_type,
                status=NodeStatus.UP.value,
                description=desc,
                last_seen=datetime.now(timezone.utc).isoformat(),
            )

        # 2. Populate Links
        for item in links_data:
            if hasattr(item, "source") and hasattr(item, "target"):
                src = item.source
                tgt = item.target
                link_id = getattr(item, "id", f"link-{src}-{tgt}")
                weight = float(getattr(item, "weight", 1.0))
                bw = float(getattr(item, "bandwidth_mbps", 100.0))
                desc = getattr(item, "description", "")
            elif isinstance(item, dict):
                src = str(item.get("source"))
                tgt = str(item.get("target"))
                link_id = item.get("id", f"link-{src}-{tgt}")
                weight = float(item.get("weight", 1.0))
                bw = float(item.get("bandwidth_mbps", item.get("bandwidth", 100.0)))
                desc = item.get("description", "")
            else:
                continue

            # Ensure both endpoint nodes exist in graph
            if not graph.has_node(src):
                graph.add_node(src, id=src, name=src, ip="", type="router", status=NodeStatus.UP.value)
            if not graph.has_node(tgt):
                graph.add_node(tgt, id=tgt, name=tgt, ip="", type="router", status=NodeStatus.UP.value)

            graph.add_edge(
                src,
                tgt,
                id=link_id,
                weight=weight,
                bandwidth=bw,
                bandwidth_mbps=bw,
                status=LinkStatus.UP.value,
                latency_ms=1.0,
                description=desc,
            )

        _current_topology = graph
        logger.info(
            "Built topology graph with {} nodes and {} edges",
            graph.number_of_nodes(),
            graph.number_of_edges(),
        )
        return graph

    def update_node_status(
        self,
        graph: nx.Graph,
        node_id: str,
        status: str | NodeStatus,
    ) -> None:
        """Update operational status and last_seen timestamp of a node.

        Args:
            graph: Target NetworkX graph.
            node_id: Node identifier.
            status: New status (UP, DOWN, DEGRADED).
        """
        if not graph.has_node(node_id):
            logger.warning("Attempted to update status for non-existent node '{}'", node_id)
            return

        stat_str = status.value if isinstance(status, NodeStatus) else str(status).lower()
        graph.nodes[node_id]["status"] = stat_str

        if stat_str == NodeStatus.UP.value:
            graph.nodes[node_id]["last_seen"] = datetime.now(timezone.utc).isoformat()

        logger.debug("Updated node '{}' status -> {}", node_id, stat_str)

    def update_link_status(
        self,
        graph: nx.Graph,
        source: str,
        target: str,
        status: str | LinkStatus,
    ) -> None:
        """Update operational status of an edge between source and target nodes.

        Args:
            graph: Target NetworkX graph.
            source: Source node ID.
            target: Target node ID.
            status: New link status (UP, DOWN, DEGRADED).
        """
        if not graph.has_edge(source, target):
            logger.warning("Attempted to update status for non-existent link '{}' - '{}'", source, target)
            return

        stat_str = status.value if isinstance(status, LinkStatus) else str(status).lower()
        graph[source][target]["status"] = stat_str
        logger.debug("Updated link '{}-{}' status -> {}", source, target, stat_str)

    def update_link_weight(
        self,
        graph: nx.Graph,
        source: str,
        target: str,
        latency_ms: float,
    ) -> None:
        """Dynamically adjust edge weight based on live observed latency.

        Higher latency increases the link cost for shortest path calculations.

        Args:
            graph: Target NetworkX graph.
            source: Source node ID.
            target: Target node ID.
            latency_ms: Measured latency in milliseconds.
        """
        if not graph.has_edge(source, target):
            logger.warning("Cannot update weight for missing edge '{}-{}'", source, target)
            return

        # Base cost scale: 1 unit per 10 ms of latency, minimum weight 1.0
        calculated_weight = max(1.0, round(float(latency_ms) / 10.0, 2))
        graph[source][target]["latency_ms"] = round(float(latency_ms), 2)
        graph[source][target]["weight"] = calculated_weight
        logger.trace(
            "Updated link '{}-{}' live latency -> {}ms (weight -> {})",
            source,
            target,
            latency_ms,
            calculated_weight,
        )

    def get_topology_snapshot(self, graph: nx.Graph | None = None) -> dict[str, Any]:
        """Serialize current topology graph into a JSON-compatible dictionary.

        Args:
            graph: NetworkX graph to snapshot (defaults to current singleton graph).

        Returns:
            Dictionary containing nodes list, links list, and summary stats.
        """
        g = graph or get_topology()

        nodes: list[dict[str, Any]] = []
        for n, attrs in g.nodes(data=True):
            node_dict = dict(attrs)
            node_dict["id"] = n
            nodes.append(node_dict)

        links: list[dict[str, Any]] = []
        for u, v, attrs in g.edges(data=True):
            link_dict = dict(attrs)
            link_dict["source"] = u
            link_dict["target"] = v
            link_dict["source_node_id"] = u
            link_dict["target_node_id"] = v
            links.append(link_dict)

        up_nodes = sum(1 for n in nodes if n.get("status") == NodeStatus.UP.value)
        down_nodes = sum(1 for n in nodes if n.get("status") == NodeStatus.DOWN.value)
        degraded_nodes = len(nodes) - up_nodes - down_nodes

        return {
            "nodes": nodes,
            "links": links,
            "summary": {
                "total_nodes": len(nodes),
                "total_links": len(links),
                "up_nodes": up_nodes,
                "down_nodes": down_nodes,
                "degraded_nodes": degraded_nodes,
            },
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }


def get_topology() -> nx.Graph:
    """Retrieve the module-level singleton topology graph, creating it if needed.

    Returns:
        The shared NetworkX graph instance.
    """
    global _current_topology
    if _current_topology is None:
        builder = TopologyBuilder()
        _current_topology = builder.build_from_config()
    return _current_topology


def set_topology(graph: nx.Graph) -> None:
    """Explicitly assign the global topology graph singleton.

    Args:
        graph: NetworkX graph to store.
    """
    global _current_topology
    _current_topology = graph
