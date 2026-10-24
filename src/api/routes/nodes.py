"""Node and Telemetry Metrics API routes.

Provides endpoints for inspecting individual nodes, listing all network devices,
and retrieving historical and real-time telemetry metrics.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from loguru import logger
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.schemas import MetricResponse, NodeResponse
from src.core.models import Metric, Node, get_database

router = APIRouter(prefix="/api/nodes", tags=["Nodes"])


async def get_db_session() -> Any:
    """FastAPI dependency yielding an async database session."""
    db = get_database()
    async with db.session_factory() as session:
        yield session


@router.get("", response_model=list[NodeResponse], summary="List all nodes")
@router.get("/", response_model=list[NodeResponse], include_in_schema=False)
async def list_nodes(
    session: AsyncSession = Depends(get_db_session),
) -> list[NodeResponse]:
    """Retrieve all monitored network nodes with current operational status."""
    result = await session.execute(select(Node).order_by(Node.id.asc()))
    nodes = result.scalars().all()
    return [NodeResponse.model_validate(node) for node in nodes]


@router.get("/{node_id}", response_model=NodeResponse, summary="Get node details")
async def get_node(
    node_id: str,
    session: AsyncSession = Depends(get_db_session),
) -> NodeResponse:
    """Retrieve details and operational status for a single node."""
    result = await session.execute(select(Node).where(Node.id == node_id))
    node = result.scalar_one_or_none()
    if not node:
        logger.warning("Node not found: {}", node_id)
        raise HTTPException(status_code=404, detail=f"Node '{node_id}' not found")
    return NodeResponse.model_validate(node)


@router.get("/{node_id}/metrics", response_model=list[MetricResponse], summary="Get node telemetry history")
async def get_node_metrics(
    node_id: str,
    limit: int = Query(default=100, ge=1, le=1000, description="Max metrics records to return"),
    offset: int = Query(default=0, ge=0, description="Record pagination offset"),
    session: AsyncSession = Depends(get_db_session),
) -> list[MetricResponse]:
    """Retrieve historical telemetry samples (latency, packet loss, jitter) for a specific node."""
    # Verify node exists
    node_check = await session.execute(select(Node).where(Node.id == node_id))
    if not node_check.scalar_one_or_none():
        raise HTTPException(status_code=404, detail=f"Node '{node_id}' not found")

    result = await session.execute(
        select(Metric)
        .where(Metric.node_id == node_id)
        .order_by(desc(Metric.recorded_at))
        .offset(offset)
        .limit(limit)
    )
    metrics = result.scalars().all()
    return [MetricResponse.model_validate(m) for m in metrics]


@router.get(
    "/{node_id}/metrics/latest",
    response_model=MetricResponse,
    summary="Get latest telemetry sample for a node",
)
async def get_latest_node_metric(
    node_id: str,
    session: AsyncSession = Depends(get_db_session),
) -> MetricResponse:
    """Retrieve the most recently recorded telemetry metric for a node."""
    # Verify node exists
    node_check = await session.execute(select(Node).where(Node.id == node_id))
    if not node_check.scalar_one_or_none():
        raise HTTPException(status_code=404, detail=f"Node '{node_id}' not found")

    result = await session.execute(
        select(Metric)
        .where(Metric.node_id == node_id)
        .order_by(desc(Metric.recorded_at))
        .limit(1)
    )
    metric = result.scalar_one_or_none()
    if not metric:
        raise HTTPException(status_code=404, detail=f"No metrics recorded yet for node '{node_id}'")
    return MetricResponse.model_validate(metric)


# ==============================================================================
# Secondary router for /api/metrics endpoints (matching frontend API service)
# ==============================================================================

metrics_router = APIRouter(prefix="/api/metrics", tags=["Metrics"])


@metrics_router.get("/node/{node_id}", response_model=list[MetricResponse], summary="Get node telemetry metrics")
async def get_metrics_by_node(
    node_id: str,
    limit: int = Query(default=50, ge=1, le=1000),
    session: AsyncSession = Depends(get_db_session),
) -> list[MetricResponse]:
    """Alias endpoint for fetching node metrics (supporting frontend clients)."""
    return await get_node_metrics(node_id=node_id, limit=limit, offset=0, session=session)
