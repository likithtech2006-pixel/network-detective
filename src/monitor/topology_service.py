"""Single place where the network's devices, wires and mode change.

The database is the source of truth for the topology. Every change here is written to
the database and then pushed to everything that keeps its own copy: the NetworkX graph,
the simulated network, the routing table (with its backup routes) and the IP list the
verifier pings.
"""

from __future__ import annotations

import ipaddress
import re
from datetime import datetime, timezone
from typing import Any

import networkx as nx
from sqlalchemy import delete, func, or_, select, update

from src.core.events import TOPOLOGY_UPDATED, EventBus
from src.core.events import event_bus as default_event_bus
from src.core.models import (
    AppSetting,
    Database,
    Incident,
    IncidentStatus,
    Link,
    LinkStatus,
    Metric,
    Node,
    NodeStatus,
)
from src.healer.route_manager import RouteManager
from src.monitor.topology_builder import TopologyBuilder, set_topology
from src.simulation.virtual_network import VirtualNetwork
from src.utils.logger import logger

NODE_TYPES = ("router", "switch", "server")
MODES = ("simulation", "live")
_HOSTNAME = re.compile(r"^(?=.{1,253}$)([A-Za-z0-9-]{1,63}\.)*[A-Za-z0-9-]{1,63}$")


class TopologyError(ValueError):
    """A requested topology change is invalid; the message says why."""

    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "device"


def _check_address(address: str) -> str:
    address = address.strip()
    try:
        return str(ipaddress.ip_address(address))
    except ValueError:
        if _HOSTNAME.match(address):
            return address
    raise TopologyError(f"'{address}' is not a valid IP address or hostname")


class TopologyService:
    """Adds and removes devices and wires, resets health and switches the network mode."""

    def __init__(
        self,
        db: Database,
        virtual_network: VirtualNetwork,
        route_manager: RouteManager,
        node_ips: dict[str, str],
        event_bus: EventBus | None = None,
    ) -> None:
        """Initialize the service.

        Args:
            db: Database holding nodes, links and settings.
            virtual_network: Simulated network kept in step with the topology.
            route_manager: Routing table rebuilt after every change.
            node_ips: Device ID -> address map shared with the verifier; updated in place.
            event_bus: Bus for TOPOLOGY_UPDATED events.
        """
        self.db = db
        self.virtual_network = virtual_network
        self.route_manager = route_manager
        self.node_ips = node_ips
        self.event_bus = event_bus or default_event_bus
        self._builder = TopologyBuilder()
        # Set after construction by the app (they need the service's graph first)
        self.health_monitor: Any = None
        self.alert_manager: Any = None
        self.incident_resolver: Any = None

    # ------------------------------------------------------------------ loading

    async def load(self) -> nx.Graph:
        """Rebuild the graph, simulation, routes and IP list from the database."""
        async with self.db.session_factory() as session:
            nodes = (await session.execute(select(Node))).scalars().all()
            links = (await session.execute(select(Link))).scalars().all()

        graph = nx.Graph()
        for n in nodes:
            status = n.status.value if isinstance(n.status, NodeStatus) else str(n.status)
            graph.add_node(
                n.id,
                id=n.id,
                name=n.name,
                ip=n.ip_address,
                ip_address=n.ip_address,
                type=n.node_type,
                node_type=n.node_type,
                status=status,
            )
        for link in links:
            if not (graph.has_node(link.source_node_id) and graph.has_node(link.target_node_id)):
                continue
            status = link.status.value if isinstance(link.status, LinkStatus) else str(link.status)
            graph.add_edge(
                link.source_node_id,
                link.target_node_id,
                id=link.id,
                weight=float(link.weight),
                bandwidth=float(link.bandwidth_mbps),
                bandwidth_mbps=float(link.bandwidth_mbps),
                status=status,
            )

        set_topology(graph)
        self.virtual_network.sync_topology(
            [
                {"id": n.id, "name": n.name, "ip_address": n.ip_address, "node_type": n.node_type}
                for n in nodes
            ],
            [
                {"source": u, "target": v, "weight": d["weight"], "bandwidth_mbps": d["bandwidth"]}
                for u, v, d in graph.edges(data=True)
            ],
        )
        self.route_manager.rebuild_routes(graph)
        self.node_ips.clear()
        self.node_ips.update({n.id: n.ip_address for n in nodes})
        await self.event_bus.publish(TOPOLOGY_UPDATED, self._builder.get_topology_snapshot(graph))
        return graph

    # ------------------------------------------------------------------ devices

    async def add_node(
        self,
        name: str,
        node_type: str,
        ip_address: str,
        pos_x: float | None = None,
        pos_y: float | None = None,
    ) -> Node:
        """Add a device and return it."""
        name = name.strip()
        if not name:
            raise TopologyError("A device needs a name")
        if node_type not in NODE_TYPES:
            raise TopologyError(f"Device type must be one of {', '.join(NODE_TYPES)}")
        address = _check_address(ip_address)

        async with self.db.session_factory() as session:
            existing = (await session.execute(select(Node))).scalars().all()
            if any(n.ip_address == address for n in existing):
                raise TopologyError(f"Another device already uses {address}", 409)
            taken = {n.id for n in existing}
            node_id, i = _slug(name), 2
            while node_id in taken:
                node_id, i = f"{_slug(name)}-{i}", i + 1
            node = Node(
                id=node_id,
                name=name,
                ip_address=address,
                node_type=node_type,
                status=NodeStatus.UP,
                pos_x=pos_x,
                pos_y=pos_y,
            )
            session.add(node)
            await session.commit()
        logger.info("Topology: added {} '{}' at {}", node_type, node_id, address)
        await self.load()
        return node

    async def update_node(self, node_id: str, changes: dict[str, Any]) -> None:
        """Rename a device, change its type or address, or move it on the canvas."""
        values: dict[str, Any] = {}
        if "name" in changes and changes["name"] is not None:
            if not str(changes["name"]).strip():
                raise TopologyError("A device needs a name")
            values["name"] = str(changes["name"]).strip()
        if changes.get("node_type") is not None:
            if changes["node_type"] not in NODE_TYPES:
                raise TopologyError(f"Device type must be one of {', '.join(NODE_TYPES)}")
            values["node_type"] = changes["node_type"]
        if changes.get("ip_address") is not None:
            values["ip_address"] = _check_address(str(changes["ip_address"]))
        for axis in ("pos_x", "pos_y"):
            if axis in changes:
                values[axis] = changes[axis]
        if not values:
            return

        async with self.db.session_factory() as session:
            node = await session.get(Node, node_id)
            if node is None:
                raise TopologyError(f"Unknown device '{node_id}'", 404)
            if "ip_address" in values:
                clash = await session.execute(
                    select(Node.id).where(
                        Node.ip_address == values["ip_address"], Node.id != node_id
                    )
                )
                if clash.first():
                    raise TopologyError(f"Another device already uses {values['ip_address']}", 409)
            await session.execute(update(Node).where(Node.id == node_id).values(**values))
            await session.commit()

        # A move only changes the drawing; anything else changes what is monitored
        if set(values) - {"pos_x", "pos_y"}:
            await self.load()

    async def remove_node(self, node_id: str) -> set[tuple[str, str]]:
        """Remove a device and its wires; return the removed wires as (source, target)."""
        async with self.db.session_factory() as session:
            if await session.get(Node, node_id) is None:
                raise TopologyError(f"Unknown device '{node_id}'", 404)
            attached = (
                await session.execute(
                    select(Link).where(
                        or_(Link.source_node_id == node_id, Link.target_node_id == node_id)
                    )
                )
            ).scalars().all()
            wires = {(link.source_node_id, link.target_node_id) for link in attached}
            await session.execute(delete(Metric).where(Metric.node_id == node_id))
            await session.execute(
                delete(Link).where(
                    or_(Link.source_node_id == node_id, Link.target_node_id == node_id)
                )
            )
            await session.execute(delete(Node).where(Node.id == node_id))
            await session.commit()
        logger.info("Topology: removed device '{}' and {} wire(s)", node_id, len(wires))
        if self.health_monitor is not None:
            await self.health_monitor.forget({node_id}, wires)
        await self.load()
        return wires

    # ------------------------------------------------------------------ wires

    async def add_link(
        self, source: str, target: str, weight: float = 1.0, bandwidth_mbps: float = 100.0
    ) -> Link:
        """Connect two devices with a wire and return it."""
        if source == target:
            raise TopologyError("A wire must connect two different devices")
        if weight <= 0 or bandwidth_mbps <= 0:
            raise TopologyError("Weight and bandwidth must be positive")
        async with self.db.session_factory() as session:
            for node_id in (source, target):
                if await session.get(Node, node_id) is None:
                    raise TopologyError(f"Unknown device '{node_id}'", 404)
            duplicate = await session.execute(
                select(Link.id).where(
                    or_(
                        (Link.source_node_id == source) & (Link.target_node_id == target),
                        (Link.source_node_id == target) & (Link.target_node_id == source),
                    )
                )
            )
            if duplicate.first():
                raise TopologyError(f"'{source}' and '{target}' are already connected", 409)
            link = Link(
                id=f"link-{source}-{target}",
                source_node_id=source,
                target_node_id=target,
                status=LinkStatus.UP,
                weight=weight,
                bandwidth_mbps=bandwidth_mbps,
            )
            session.add(link)
            await session.commit()
        logger.info("Topology: connected '{}' <-> '{}'", source, target)
        await self.load()
        return link

    async def remove_link(self, link_id: str) -> None:
        """Remove one wire."""
        async with self.db.session_factory() as session:
            link = await session.get(Link, link_id)
            if link is None:
                raise TopologyError(f"Unknown wire '{link_id}'", 404)
            pair = (link.source_node_id, link.target_node_id)
            await session.delete(link)
            await session.commit()
        logger.info("Topology: removed wire '{}'", link_id)
        if self.health_monitor is not None:
            await self.health_monitor.forget(set(), {pair})
        await self.load()

    # ------------------------------------------------------------------ health and mode

    async def reset_health(self, note: str) -> None:
        """Mark everything healthy, clear monitor state and close open incidents.

        Args:
            note: Appended to each incident closed by the reset.
        """
        if self.health_monitor is not None:
            await self.health_monitor.reset()
        if self.alert_manager is not None:
            self.alert_manager.release_all()
        self.virtual_network.reset()

        async with self.db.session_factory() as session:
            await session.execute(update(Node).values(status=NodeStatus.UP))
            await session.execute(update(Link).values(status=LinkStatus.UP))
            await session.execute(
                update(Incident)
                .where(Incident.status != IncidentStatus.VERIFIED, Incident.resolved_at.is_(None))
                .values(
                    resolved_at=datetime.now(timezone.utc),
                    resolution_notes=func.coalesce(Incident.resolution_notes + " ", "") + note,
                )
            )
            await session.commit()
        await self.load()

    async def get_mode(self) -> str:
        """Return the saved network mode ("simulation" by default)."""
        async with self.db.session_factory() as session:
            setting = await session.get(AppSetting, "network_mode")
        return setting.value if setting and setting.value in MODES else "simulation"

    async def set_mode(self, mode: str) -> None:
        """Switch between the simulated network and pinging real devices, and save the choice."""
        if mode not in MODES:
            raise TopologyError(f"Mode must be one of {', '.join(MODES)}")
        async with self.db.session_factory() as session:
            await session.merge(AppSetting(key="network_mode", value=mode))
            await session.commit()
        await self.apply_mode(mode)
        await self.reset_health(f"Closed when switching to {mode} mode.")
        logger.info("Network mode set to {}", mode)

    async def apply_mode(self, mode: str) -> None:
        """Point the monitor and the verifier at the simulation or at real devices."""
        if self.health_monitor is not None:
            await self.health_monitor.set_mode(mode)
        if self.incident_resolver is not None:
            checker = self.incident_resolver.connectivity_checker
            checker.virtual_network = None if mode == "live" else self.virtual_network


__all__ = ["MODES", "NODE_TYPES", "TopologyError", "TopologyService"]
