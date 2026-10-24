"""Main FastAPI application entry point for Network Detective & Self-Healing Network.

Configures application lifespan (database initialization, topology seeding,
scheduler, and event bus), middleware, routers, and Uvicorn runtime runner.
"""

from __future__ import annotations

import contextlib
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Any

import uvicorn

try:
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
except ImportError:
    AsyncIOScheduler = None  # type: ignore[assignment,misc]
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select

from loguru import logger
from src.api.routes import router as default_api_router
from src.api.routes.config import router as config_router
from src.api.routes.dashboard import router as dashboard_router
from src.api.routes.incidents import router as incidents_router
from src.api.routes.nodes import metrics_router
from src.api.routes.nodes import router as nodes_router
from src.api.routes.simulator import (
    get_sim_network,
    simulator_alias_router,
)
from src.api.routes.simulator import (
    router as simulator_router,
)
from src.api.routes.topology import router as topology_router
from src.api.websocket import router as websocket_router
from src.core.config import Settings, get_settings
from src.core.events import FAULT_DETECTED, HEALING_COMPLETE, TOPOLOGY_UPDATED, event_bus
from src.core.models import Link, LinkStatus, Node, NodeStatus, get_database
from src.healer.route_manager import RouteManager
from src.healer.self_healer import SelfHealer
from src.healer.traffic_redirector import TrafficRedirector
from src.monitor.topology_builder import get_topology
from src.utils.logger import setup_logger
from src.verifier.connectivity_checker import ConnectivityChecker
from src.verifier.incident_resolver import IncidentResolver
from src.verifier.validation_engine import ValidationEngine


async def _seed_topology(settings: Settings) -> None:
    """Seed initial network nodes and links from YAML configuration into the database."""
    db = get_database(settings.database_url)
    async with db.session_factory() as session:
        # Check existing nodes
        result_nodes = await session.execute(select(Node))
        existing_nodes = {node.id: node for node in result_nodes.scalars().all()}

        for node_cfg in settings.topology.nodes:
            if node_cfg.id not in existing_nodes:
                logger.info("Seeding node: {} ({})", node_cfg.id, node_cfg.ip_address)
                new_node = Node(
                    id=node_cfg.id,
                    name=node_cfg.name,
                    ip_address=node_cfg.ip_address,
                    node_type=node_cfg.node_type,
                    status=NodeStatus.UP,
                )
                session.add(new_node)

        await session.flush()

        # Check existing links
        result_links = await session.execute(select(Link))
        existing_links = {link.id: link for link in result_links.scalars().all()}

        for link_cfg in settings.topology.links:
            link_id = link_cfg.id or f"link-{link_cfg.source}-{link_cfg.target}"
            if link_id not in existing_links:
                logger.info("Seeding link: {} -> {} (weight={})", link_cfg.source, link_cfg.target, link_cfg.weight)
                new_link = Link(
                    id=link_id,
                    source_node_id=link_cfg.source,
                    target_node_id=link_cfg.target,
                    status=LinkStatus.UP,
                    weight=link_cfg.weight,
                    bandwidth_mbps=link_cfg.bandwidth_mbps,
                )
                session.add(new_link)

        await session.commit()

    # Emit topology updated event
    await event_bus.publish(
        TOPOLOGY_UPDATED,
        {
            "nodes_count": len(settings.topology.nodes),
            "links_count": len(settings.topology.links),
            "topology_name": settings.topology.name,
        },
    )


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan context manager for startup and shutdown procedures."""
    settings = get_settings()
    setup_logger(settings.log_level)
    logger.info("Starting {} in [{}] mode...", settings.app_name, settings.environment)

    # 1. Initialize Database Schema
    db = get_database(settings.database_url)
    logger.info("Initializing database schema at: {}", settings.database_url)
    await db.create_all()
    app.state.db = db

    # 2. Build / Seed Initial Topology
    logger.info("Loading initial network topology: '{}'", settings.topology.name)
    await _seed_topology(settings)

    # 3. Start Scheduler
    scheduler = None
    if AsyncIOScheduler is not None:
        try:
            scheduler = AsyncIOScheduler()
            scheduler.start()
            logger.info("AsyncIOScheduler started successfully.")
        except Exception as exc:
            logger.warning("Could not start AsyncIOScheduler: {}", exc)
            scheduler = None
    else:
        logger.info("APScheduler not installed; running in event-driven mode.")
    app.state.scheduler = scheduler

    # 4. Wire the self-healing loop: FAULT_DETECTED -> SelfHealer -> HEALING_COMPLETE -> IncidentResolver
    route_manager = RouteManager()
    route_manager.rebuild_routes(get_topology())
    self_healer = SelfHealer(
        route_manager=route_manager,
        traffic_redirector=TrafficRedirector(route_manager, simulation_mode=True),
        event_bus=event_bus,
        db=db,
    )
    incident_resolver = IncidentResolver(
        connectivity_checker=ConnectivityChecker(virtual_network=get_sim_network()),
        validation_engine=ValidationEngine(),
        event_bus=event_bus,
        healer=self_healer,
        node_ips={n.id: n.ip_address for n in settings.topology.nodes},
        db=db,
    )
    app.state.self_healer = self_healer
    app.state.incident_resolver = incident_resolver

    # 5. Attach Event Bus
    app.state.event_bus = event_bus
    logger.info("EventBus initialized with {} active listeners.", event_bus.subscriber_count())

    yield

    # Shutdown sequence
    logger.info("Shutting down application...")
    event_bus.unsubscribe(FAULT_DETECTED, self_healer.on_fault_detected)
    event_bus.unsubscribe(HEALING_COMPLETE, incident_resolver.on_healing_complete)
    if scheduler and getattr(scheduler, "running", False):
        scheduler.shutdown(wait=False)
        logger.info("AsyncIOScheduler stopped.")

    await db.close()
    logger.info("Database connections closed.")


def create_app() -> FastAPI:
    """Construct and configure the FastAPI application instance."""
    settings = get_settings()

    app = FastAPI(
        title=settings.app_name,
        description=(
            "Network Detective & Self-Healing Network: Real-time network monitoring, "
            "automated root-cause diagnosis, and autonomous remediation."
        ),
        version="0.1.0",
        debug=settings.debug,
        lifespan=lifespan,
    )

    # CORS Middleware (permits frontend requests)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Include API Routers
    app.include_router(default_api_router, prefix="/api")
    app.include_router(topology_router)
    app.include_router(nodes_router)
    app.include_router(metrics_router)
    app.include_router(incidents_router)
    app.include_router(simulator_router)
    app.include_router(simulator_alias_router)
    app.include_router(config_router)
    app.include_router(dashboard_router)
    app.include_router(websocket_router)

    # Mount static files directory if present
    project_root = Path(__file__).resolve().parent.parent
    static_dir = project_root / "static"
    if static_dir.is_dir():
        app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    @app.get("/", tags=["Root"])
    async def root() -> dict[str, Any]:
        """Root status and documentation entry point."""
        return {
            "name": settings.app_name,
            "version": "0.1.0",
            "status": "online",
            "docs_url": "/docs",
            "api_url": "/api",
        }

    return app


# Application singleton
app = create_app()


def run() -> None:
    """CLI executable target called by the 'network-detective' console script."""
    settings = get_settings()
    setup_logger(settings.log_level)
    uvicorn.run(
        "src.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
        log_config=None,
    )


if __name__ == "__main__":
    run()
