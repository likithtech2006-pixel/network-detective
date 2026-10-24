"""Simulation API routes for injecting and recovering network faults.

Provides control endpoints to simulate hardware failures, link severed events,
performance degradations, and full network resets for self-healing verification.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import networkx as nx
from fastapi import APIRouter, HTTPException, Request
from loguru import logger
from sqlalchemy import func, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.schemas import (
    MessageResponse,
    SimulateFailureRequest,
    SimulateRecoverRequest,
    SimulationStatusResponse,
)
from src.core.events import event_bus
from src.core.models import (
    Incident,
    IncidentStatus,
    LinkStatus,
    NodeStatus,
    get_database,
)
from src.monitor.topology_builder import get_topology
from src.simulation.failure_injector import FailureInjector
from src.simulation.virtual_network import VirtualNetwork

router = APIRouter(prefix="/api/simulate", tags=["Simulator"])

# Global simulation singleton instances
_virtual_network: VirtualNetwork | None = None
_failure_injector: FailureInjector | None = None


def get_sim_network() -> VirtualNetwork:
    """Obtain or initialize the VirtualNetwork simulation singleton."""
    global _virtual_network
    if _virtual_network is None:
        _virtual_network = VirtualNetwork()
    return _virtual_network


def get_injector() -> FailureInjector:
    """Obtain or initialize the FailureInjector singleton."""
    global _failure_injector
    if _failure_injector is None:
        vn = get_sim_network()
        _failure_injector = FailureInjector(virtual_network=vn, event_bus=event_bus)
    return _failure_injector


async def get_db_session() -> Any:
    """FastAPI dependency yielding an async database session."""
    db = get_database()
    async with db.session_factory() as session:
        yield session


def _parse_link_endpoints(
    component_id: str, target_id: str | None, graph: nx.Graph
) -> tuple[str, str]:
    """Extract source and target node identifiers for a link."""
    if target_id:
        return component_id, target_id

    # Configured link IDs such as 'link-b-c' are stored on the topology edges
    for u, v, data in graph.edges(data=True):
        if data.get("id") == component_id:
            return str(u), str(v)

    # Handle 'link-router-b-switch-c' or 'router-b-switch-c' (node IDs may contain hyphens)
    cleaned = component_id.removeprefix("link-")
    for node in graph.nodes:
        prefix = f"{node}-"
        if cleaned.startswith(prefix) and cleaned[len(prefix):] in graph:
            return str(node), cleaned[len(prefix):]

    for sep in ["->", "_"]:
        if sep in cleaned:
            parts = cleaned.split(sep, 1)
            return parts[0].strip(), parts[1].strip()

    raise ValueError(f"Could not determine source and target from link identifier '{component_id}'")


async def _close_open_incidents(
    session: AsyncSession, components: list[str] | None, note: str
) -> None:
    """Close open incidents once their component has been restored by hand.

    The status is left as it was (an escalated incident stays escalated), so closing
    an incident never counts it as self-healed; only resolved_at and the note change.

    Args:
        session: Active database session (caller commits).
        components: Affected component IDs to close, or None to close every open incident.
        note: Note appended to each closed incident's resolution notes.
    """
    stmt = update(Incident).where(
        Incident.status != IncidentStatus.VERIFIED, Incident.resolved_at.is_(None)
    )
    if components is not None:
        stmt = stmt.where(Incident.affected_component.in_(components))
    await session.execute(
        stmt.values(
            resolved_at=datetime.now(timezone.utc),
            resolution_notes=func.coalesce(Incident.resolution_notes + " ", "") + note,
        )
    )


def _rebuild_routes(request: Request, topology: nx.Graph) -> None:
    """Recompute the self-healer's routing table after components come back up."""
    healer = getattr(request.app.state, "self_healer", None)
    if healer is not None:
        healer.route_manager.rebuild_routes(topology)


@router.post("/fail", response_model=MessageResponse, summary="Inject network failure")
@router.post("/failure", response_model=MessageResponse, include_in_schema=False)
async def inject_failure(req: SimulateFailureRequest, request: Request) -> MessageResponse:
    """Break a node or link in the simulated network.

    Only the simulated physical layer changes here. The HealthMonitor has to notice the
    failure on its probes, diagnose it and raise the incident that starts self-healing,
    so the call returns at once and the outcome appears in /api/incidents shortly after.
    """
    injector = get_injector()
    topology = get_topology()

    comp_type = req.component_type.lower()
    comp_id = req.component_id.strip()

    if not comp_id:
        raise HTTPException(status_code=400, detail="Missing required 'component_id' or 'target_id'")

    logger.warning("API simulation request: fail {} '{}' (target={})", comp_type, comp_id, req.target_id)

    if comp_type == "node":
        if comp_id not in topology.nodes:
            raise HTTPException(status_code=404, detail=f"Unknown node '{comp_id}'")
        if request.app.state.health_monitor.mode == "live":
            raise HTTPException(
                status_code=409,
                detail="Live mode pings real devices: switch the device off or unplug it instead. "
                "Wires can still be cut here.",
            )

        fault = (req.fault_type or "node_down").lower()
        if fault in ["high_latency", "packet_loss", "link_degraded", "degraded"]:
            await injector.inject_degradation(node_id=comp_id, latency_ms=350.0, loss_pct=25.0)
            msg = f"Degraded node '{comp_id}' (350 ms latency, 25% loss)"
        else:
            await injector.inject_node_failure(comp_id)
            msg = f"Crashed node '{comp_id}'"

    elif comp_type == "link":
        try:
            src, tgt = _parse_link_endpoints(comp_id, req.target_id, topology)
        except ValueError as err:
            raise HTTPException(status_code=400, detail=str(err)) from err
        if not topology.has_edge(src, tgt):
            raise HTTPException(status_code=404, detail=f"Unknown link '{comp_id}'")

        await injector.inject_link_failure(src, tgt)
        msg = f"Cut link between '{src}' and '{tgt}'"
    else:
        raise HTTPException(status_code=400, detail=f"Unsupported component_type: {comp_type}")

    return MessageResponse(
        status="ok",
        message=f"{msg}; the health monitor will detect it.",
        data={"component_type": comp_type, "component_id": comp_id, "target_id": req.target_id},
    )


@router.post("/recover", response_model=MessageResponse, summary="Recover failed component")
async def recover_component(req: SimulateRecoverRequest) -> MessageResponse:
    """Repair a failed or degraded component in the simulated network.

    The HealthMonitor sees the component answer again, restores its status, fails routes
    back to the primary paths and closes its incident.
    """
    injector = get_injector()
    topology = get_topology()

    comp_type = req.component_type.lower()
    comp_id = req.component_id.strip()

    if not comp_id:
        raise HTTPException(status_code=400, detail="Missing required 'component_id' or 'target_id'")

    logger.info("API simulation request: recover {} '{}' (target={})", comp_type, comp_id, req.target_id)

    if comp_type == "node":
        await injector.recover_node(comp_id)
        msg = f"Node '{comp_id}' repaired"

    elif comp_type == "link":
        try:
            src, tgt = _parse_link_endpoints(comp_id, req.target_id, topology)
        except ValueError as err:
            raise HTTPException(status_code=400, detail=str(err)) from err
        await injector.recover_link(src, tgt)
        msg = f"Link '{src}' <-> '{tgt}' repaired"
    else:
        raise HTTPException(status_code=400, detail=f"Unsupported component_type: {comp_type}")

    return MessageResponse(
        status="ok",
        message=f"{msg}; the health monitor will confirm recovery.",
        data={"component_type": comp_type, "component_id": comp_id},
    )


@router.post("/reset", response_model=MessageResponse, summary="Reset network simulation")
async def reset_simulation(request: Request) -> MessageResponse:
    """Repair every simulated fault, mark all devices healthy and close open incidents."""
    logger.info("API simulation request: RESET entire network")
    await request.app.state.topology_service.reset_health("Closed: network reset to healthy baseline.")
    return MessageResponse(
        status="ok",
        message="Simulated network successfully reset to baseline healthy state",
    )


@router.get("/status", response_model=SimulationStatusResponse, summary="Get simulation state")
async def get_simulation_status() -> SimulationStatusResponse:
    """Retrieve current list of active failures, degraded links, and injection history."""
    vn = get_sim_network()
    nodes = vn.get_all_nodes()
    links = vn.get_all_links()

    failed_nodes = [
        nid
        for nid, data in nodes.items()
        if data.get("status") in [NodeStatus.DOWN, "down"]
    ]
    degraded_nodes = [
        nid
        for nid, data in nodes.items()
        if data.get("status") in [NodeStatus.DEGRADED, "degraded"]
    ]

    failed_links = [
        f"link-{src}-{tgt}"
        for (src, tgt), data in links.items()
        if data.get("status") in [LinkStatus.DOWN, "down"]
    ]

    degraded_links = [
        {
            "link": f"link-{src}-{tgt}",
            "source": src,
            "target": tgt,
            "latency_ms": data.get("latency_ms"),
            "packet_loss_pct": data.get("packet_loss_pct"),
        }
        for (src, tgt), data in links.items()
        if data.get("status") in [LinkStatus.DEGRADED, "degraded"]
        or float(data.get("latency_ms", 0)) > 50.0
    ]

    injector = get_injector()
    active = bool(failed_nodes or failed_links or degraded_links or degraded_nodes)

    return SimulationStatusResponse(
        simulation_active=active,
        failed_nodes=failed_nodes,
        failed_links=failed_links,
        degraded_links=degraded_links,
        active_injections=injector._history[-15:],
    )


# ==============================================================================
# Secondary alias router mounted at /api/simulator (for frontend compatibility)
# ==============================================================================

simulator_alias_router = APIRouter(prefix="/api/simulator", tags=["Simulator"])
simulator_alias_router.add_api_route("/failure", inject_failure, methods=["POST"], response_model=MessageResponse)
simulator_alias_router.add_api_route("/fail", inject_failure, methods=["POST"], response_model=MessageResponse)
simulator_alias_router.add_api_route("/recover", recover_component, methods=["POST"], response_model=MessageResponse)
simulator_alias_router.add_api_route("/reset", reset_simulation, methods=["POST"], response_model=MessageResponse)
simulator_alias_router.add_api_route("/status", get_simulation_status, methods=["GET"], response_model=SimulationStatusResponse)
