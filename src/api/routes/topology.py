"""Topology API routes.

Provides endpoints for querying the full NetworkX topology graph with node positions,
link states, and lightweight topology snapshots for real-time visualization.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
import networkx as nx
from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.schemas import LinkResponse, NodeResponse, TopologyResponse
from src.core.models import Link, Node, get_database
from src.monitor.topology_builder import TopologyBuilder, get_topology

router = APIRouter(prefix="/api/topology", tags=["Topology"])

# Fixed coordinates for campus network and mesh topology visualization layout
DEFAULT_LAYOUT: dict[str, tuple[float, float]] = {
    # 5-Node Campus Topology - Non-overlapping hierarchical layout
    "router-a": (90.0, 210.0),
    "router-b": (360.0, 90.0),
    "switch-c": (360.0, 330.0),
    "server-d": (650.0, 90.0),
    "server-e": (650.0, 330.0),
    # 7-Node Multi-Tier Mesh
    "node-core-1": (260.0, 70.0),
    "node-core-2": (500.0, 70.0),
    "node-edge-1": (120.0, 200.0),
    "node-edge-2": (380.0, 200.0),
    "node-edge-3": (640.0, 200.0),
    "node-gw-1": (240.0, 330.0),
    "node-gw-2": (520.0, 330.0),
}


async def get_db_session() -> Any:
    """FastAPI dependency for obtaining an async database session."""
    db = get_database()
    async with db.session_factory() as session:
        yield session


def _compute_positions(graph: nx.Graph) -> dict[str, tuple[float, float]]:
    """Compute 2D coordinates for nodes, using default layout or spring layout."""
    positions: dict[str, tuple[float, float]] = {}
    missing_nodes = [n for n in graph.nodes if n not in DEFAULT_LAYOUT]

    # Assign preset layout positions
    for node_id in graph.nodes:
        if node_id in DEFAULT_LAYOUT:
            positions[node_id] = DEFAULT_LAYOUT[node_id]

    # Compute spring layout coordinates for any unmapped nodes
    if missing_nodes:
        try:
            spring_pos = nx.spring_layout(graph, seed=42)
            for n in missing_nodes:
                x, y = spring_pos.get(n, (0.5, 0.5))
                # Scale to canvas space [100, 800]
                positions[n] = (float(x * 600 + 200), float(y * 400 + 100))
        except Exception as exc:
            logger.debug("Failed to calculate spring layout: {}", exc)
            for idx, n in enumerate(missing_nodes):
                positions[n] = (float(200 + idx * 100), 200.0)

    return positions


@router.get("", response_model=TopologyResponse, summary="Get full network topology")
@router.get("/", response_model=TopologyResponse, include_in_schema=False)
async def get_full_topology(
    session: AsyncSession = Depends(get_db_session),
) -> TopologyResponse:
    """Return complete network topology graph including nodes, links, and layout coordinates.

    Syncs status between the in-memory NetworkX graph and the database records.
    """
    graph = get_topology()
    positions = _compute_positions(graph)

    # 1. Fetch persistent nodes & links from database
    nodes_query = await session.execute(select(Node))
    db_nodes = {n.id: n for n in nodes_query.scalars().all()}

    links_query = await session.execute(select(Link))
    db_links = {l.id: l for l in links_query.scalars().all()}

    # 2. Build NodeResponse list
    node_responses: list[NodeResponse] = []
    for node_id in sorted(graph.nodes):
        node_data = graph.nodes[node_id]
        db_node = db_nodes.get(node_id)

        # Merge data: database takes precedence for status, graph provides attributes
        name = db_node.name if db_node else node_data.get("name", node_id)
        ip = db_node.ip_address if db_node else node_data.get("ip_address", node_data.get("ip", ""))
        node_type = db_node.node_type if db_node else node_data.get("node_type", node_data.get("type", "router"))
        status = db_node.status if db_node else node_data.get("status", "up")
        last_seen = db_node.last_seen if db_node else None

        pos = positions.get(node_id, (200.0, 200.0))

        node_responses.append(
            NodeResponse(
                id=node_id,
                name=name,
                ip_address=ip,
                node_type=node_type,
                status=status,
                last_seen=last_seen,
                x=round(pos[0], 2),
                y=round(pos[1], 2),
            )
        )

    # 3. Build LinkResponse list
    link_responses: list[LinkResponse] = []
    for u, v, link_data in graph.edges(data=True):
        link_id = link_data.get("id", f"link-{u}-{v}")
        db_link = db_links.get(link_id)

        status = db_link.status if db_link else link_data.get("status", "up")
        weight = float(db_link.weight if db_link else link_data.get("weight", 1.0))
        bandwidth = float(db_link.bandwidth_mbps if db_link else link_data.get("bandwidth_mbps", 100.0))

        link_responses.append(
            LinkResponse(
                id=link_id,
                source_node_id=u,
                target_node_id=v,
                source=u,
                target=v,
                status=status,
                weight=weight,
                bandwidth_mbps=bandwidth,
            )
        )

    # 4. Compile metadata
    metadata = {
        "node_count": len(node_responses),
        "link_count": len(link_responses),
        "graph_diameter": nx.diameter(graph) if nx.is_connected(graph) else None,
        "is_connected": nx.is_connected(graph),
    }

    return TopologyResponse(nodes=node_responses, links=link_responses, metadata=metadata)


@router.get("/snapshot", summary="Get lightweight topology snapshot")
async def get_snapshot() -> dict[str, Any]:
    """Return a simplified, lightweight snapshot of nodes and links for graph visualization.

    Directly queries the TopologyBuilder snapshot serializer.
    """
    builder = TopologyBuilder()
    graph = get_topology()
    return builder.get_topology_snapshot(graph)
