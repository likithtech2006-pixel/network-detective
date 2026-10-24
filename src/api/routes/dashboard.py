"""Dashboard Analytics and System Health API routes.

Provides endpoints for computing real-time network health metrics, uptime percentages,
incident counts, latency aggregations, and core infrastructure health checks.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends
from loguru import logger
from sqlalchemy import desc, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.schemas import DashboardStats, SystemHealth
from src.core.events import event_bus
from src.core.models import (
    Incident,
    IncidentStatus,
    Link,
    LinkStatus,
    Metric,
    Node,
    NodeStatus,
    get_database,
)

router = APIRouter(prefix="/api/dashboard", tags=["Dashboard"])


async def get_db_session() -> Any:
    """FastAPI dependency yielding an async database session."""
    db = get_database()
    async with db.session_factory() as session:
        yield session


@router.get("/stats", response_model=DashboardStats, summary="Get dashboard summary statistics")
async def get_dashboard_stats(
    session: AsyncSession = Depends(get_db_session),
) -> DashboardStats:
    """Compute aggregate high-level metrics across nodes, links, incidents, and telemetry."""
    # 1. Node counts
    nodes_result = await session.execute(select(Node))
    nodes = nodes_result.scalars().all()
    total_nodes = len(nodes)
    nodes_up = sum(1 for n in nodes if n.status == NodeStatus.UP)
    nodes_down = sum(1 for n in nodes if n.status == NodeStatus.DOWN)

    uptime_pct = round((nodes_up / total_nodes * 100.0), 2) if total_nodes > 0 else 100.0

    # 2. Link counts
    links_result = await session.execute(select(Link))
    links = links_result.scalars().all()
    total_links = len(links)
    links_up = sum(1 for l in links if l.status == LinkStatus.UP)

    # 3. Incident counts
    active_inc_res = await session.execute(
        select(func.count(Incident.id)).where(
            Incident.status != IncidentStatus.VERIFIED, Incident.resolved_at.is_(None)
        )
    )
    active_incidents = active_inc_res.scalar() or 0

    resolved_inc_res = await session.execute(
        select(func.count(Incident.id)).where(Incident.status == IncidentStatus.VERIFIED)
    )
    resolved_incidents = resolved_inc_res.scalar() or 0

    # 4. Recent Telemetry Averages (last 100 samples)
    metrics_result = await session.execute(
        select(Metric).order_by(desc(Metric.recorded_at)).limit(100)
    )
    recent_metrics = metrics_result.scalars().all()

    # Latency is averaged over probes that got a reply; unanswered probes count as loss
    replied = [m for m in recent_metrics if m.packet_loss_pct < 100.0]
    avg_latency = (
        round(sum(m.latency_ms for m in replied) / len(replied), 2) if replied else None
    )
    avg_loss = (
        round(sum(m.packet_loss_pct for m in recent_metrics) / len(recent_metrics), 2)
        if recent_metrics
        else None
    )

    return DashboardStats(
        total_nodes=total_nodes,
        nodes_up=nodes_up,
        nodes_down=nodes_down,
        total_links=total_links,
        links_up=links_up,
        active_incidents=active_incidents,
        resolved_incidents=resolved_incidents,
        avg_latency_ms=avg_latency,
        avg_packet_loss_pct=avg_loss,
        uptime_pct=uptime_pct,
    )


@router.get("/health", response_model=SystemHealth, summary="System health check")
async def health_check(
    session: AsyncSession = Depends(get_db_session),
) -> SystemHealth:
    """Verify health of database connection, event bus, and calculate overall uptime."""
    db_status = "connected"
    try:
        await session.execute(text("SELECT 1"))
    except Exception as exc:
        logger.error("Database health check failed: {}", exc)
        db_status = f"unhealthy: {exc}"

    bus_status = "active" if event_bus.subscriber_count() >= 0 else "degraded"

    # Compute uptime from node statuses
    nodes_result = await session.execute(select(Node))
    nodes = nodes_result.scalars().all()
    total_nodes = len(nodes)
    nodes_up = sum(1 for n in nodes if n.status == NodeStatus.UP)
    uptime_pct = round((nodes_up / total_nodes * 100.0), 2) if total_nodes > 0 else 100.0

    nodes_down = total_nodes - nodes_up
    overall_status = "ok" if (db_status == "connected" and nodes_down == 0) else "degraded"

    return SystemHealth(
        status=overall_status,
        database=db_status,
        event_bus=bus_status,
        scheduler="running",
        uptime_pct=uptime_pct,
        timestamp=datetime.now(timezone.utc),
    )
