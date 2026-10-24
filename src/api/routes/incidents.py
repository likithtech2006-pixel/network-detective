"""Incident Management API routes.

Provides endpoints for listing detected network failures, inspecting incident
remediation history with healing actions, filtering active incidents, and statistics.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from loguru import logger
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.api.schemas import (
    HealingActionResponse,
    IncidentResponse,
    IncidentStatsResponse,
)
from src.core.models import (
    FaultType,
    HealingAction,
    Incident,
    IncidentStatus,
    get_database,
)

router = APIRouter(prefix="/api/incidents", tags=["Incidents"])


async def get_db_session() -> Any:
    """FastAPI dependency yielding an async database session."""
    db = get_database()
    async with db.session_factory() as session:
        yield session


def _map_incident(inc: Incident) -> IncidentResponse:
    """Serialize an Incident ORM model with its healing actions to an IncidentResponse schema."""
    actions = [
        HealingActionResponse(
            id=act.id,
            incident_id=act.incident_id,
            action_type=act.action_type.value if hasattr(act.action_type, "value") else str(act.action_type),
            old_route=act.old_route,
            new_route=act.new_route,
            result=act.result.value if hasattr(act.result, "value") else str(act.result),
            executed_at=act.executed_at,
        )
        for act in inc.healing_actions
    ]

    return IncidentResponse(
        id=inc.id,
        fault_type=inc.fault_type.value if hasattr(inc.fault_type, "value") else str(inc.fault_type),
        affected_component=inc.affected_component,
        status=inc.status.value if hasattr(inc.status, "value") else str(inc.status),
        source_node=inc.source_node,
        target_node=inc.target_node,
        original_path=inc.original_path,
        alternate_path=inc.alternate_path,
        detected_at=inc.detected_at,
        resolved_at=inc.resolved_at,
        resolution_notes=inc.resolution_notes,
        healing_actions=actions,
    )


@router.get("", response_model=list[IncidentResponse], summary="List incidents")
@router.get("/", response_model=list[IncidentResponse], include_in_schema=False)
async def list_incidents(
    status: str | None = Query(default=None, description="Filter by IncidentStatus (e.g. 'detected', 'verified')"),
    limit: int = Query(default=100, ge=1, le=1000, description="Max incidents to return"),
    offset: int = Query(default=0, ge=0, description="Pagination offset"),
    session: AsyncSession = Depends(get_db_session),
) -> list[IncidentResponse]:
    """Retrieve network incidents ordered by detection time (newest first)."""
    stmt = (
        select(Incident)
        .options(selectinload(Incident.healing_actions))
        .order_by(desc(Incident.detected_at))
        .offset(offset)
        .limit(limit)
    )

    if status:
        stat_lower = status.lower()
        stmt = stmt.where(func.lower(Incident.status) == stat_lower)

    result = await session.execute(stmt)
    incidents = result.scalars().all()
    return [_map_incident(inc) for inc in incidents]


@router.get("/active", response_model=list[IncidentResponse], summary="List active unresolved incidents")
async def get_active_incidents(
    session: AsyncSession = Depends(get_db_session),
) -> list[IncidentResponse]:
    """Retrieve only ongoing, active incidents (excluding VERIFIED/resolved)."""
    stmt = (
        select(Incident)
        .options(selectinload(Incident.healing_actions))
        .where(Incident.status != IncidentStatus.VERIFIED, Incident.resolved_at.is_(None))
        .order_by(desc(Incident.detected_at))
    )
    result = await session.execute(stmt)
    incidents = result.scalars().all()
    return [_map_incident(inc) for inc in incidents]


@router.get("/stats", response_model=IncidentStatsResponse, summary="Get incident statistics")
async def get_incident_stats(
    session: AsyncSession = Depends(get_db_session),
) -> IncidentStatsResponse:
    """Calculate aggregate statistics across all recorded incidents."""
    result = await session.execute(select(Incident))
    all_incidents = result.scalars().all()

    total = len(all_incidents)
    by_status: dict[str, int] = {}
    by_fault_type: dict[str, int] = {}
    resolution_durations: list[float] = []

    for inc in all_incidents:
        # Group by status
        stat_key = inc.status.value if hasattr(inc.status, "value") else str(inc.status)
        by_status[stat_key] = by_status.get(stat_key, 0) + 1

        # Group by fault type
        fault_key = inc.fault_type.value if hasattr(inc.fault_type, "value") else str(inc.fault_type)
        by_fault_type[fault_key] = by_fault_type.get(fault_key, 0) + 1

        # Calculate resolution duration for resolved incidents
        if inc.resolved_at and inc.detected_at:
            delta = (inc.resolved_at - inc.detected_at).total_seconds()
            if delta >= 0:
                resolution_durations.append(delta)

    active_count = sum(
        1 for inc in all_incidents if inc.status != IncidentStatus.VERIFIED and inc.resolved_at is None
    )
    resolved_count = by_status.get(IncidentStatus.VERIFIED.value, 0)
    avg_duration = (
        round(sum(resolution_durations) / len(resolution_durations), 2)
        if resolution_durations
        else None
    )

    return IncidentStatsResponse(
        total_incidents=total,
        active_incidents=active_count,
        resolved_incidents=resolved_count,
        by_status=by_status,
        by_fault_type=by_fault_type,
        avg_resolution_time_sec=avg_duration,
    )


@router.get("/{incident_id}", response_model=IncidentResponse, summary="Get incident details")
async def get_incident(
    incident_id: str,
    session: AsyncSession = Depends(get_db_session),
) -> IncidentResponse:
    """Retrieve detailed state and associated healing actions for a specific incident."""
    stmt = (
        select(Incident)
        .options(selectinload(Incident.healing_actions))
        .where(Incident.id == incident_id)
    )
    result = await session.execute(stmt)
    incident = result.scalar_one_or_none()

    if not incident:
        logger.warning("Incident not found: {}", incident_id)
        raise HTTPException(status_code=404, detail=f"Incident '{incident_id}' not found")

    return _map_incident(incident)
