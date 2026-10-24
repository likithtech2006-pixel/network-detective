"""In-memory virtual network simulation environment for probing and fault emulation."""

from __future__ import annotations

import asyncio
import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from src.core.config import get_settings
from src.core.models import LinkStatus, NodeStatus
from src.utils.logger import logger


@dataclass
class SimulatedResponse:
    """Simulated ping or telemetry probe response for a network component."""

    reachable: bool
    latency_ms: float
    packet_loss_pct: float
    status: str = "up"
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert response to dictionary format."""
        return {
            "reachable": self.reachable,
            "latency_ms": self.latency_ms,
            "packet_loss_pct": self.packet_loss_pct,
            "status": self.status,
            "details": self.details,
        }


class VirtualNetwork:
    """In-memory simulated network emulator that probes and diagnostic monitors target.

    Maintains the simulated operational state (UP, DOWN, DEGRADED, latency, packet loss)
    for all nodes and links defined in the network topology configuration. Thread-safe
    via asyncio.Lock for concurrent probing and failure injection.
    """

    # Per-hop forwarding delay of a healthy device
    DEFAULT_NODE_LATENCY_MS: float = 0.6
    # Fallback for links with no weight or bandwidth configured
    DEFAULT_LINK_LATENCY_MS: float = 2.0
    # Propagation delay per unit of configured link weight (weight stands in for distance)
    PROPAGATION_MS_PER_WEIGHT: float = 2.0
    # Frame size used for serialization delay (one full Ethernet MTU)
    FRAME_BITS: int = 1500 * 8
    # Healthy measurements vary by up to this fraction, like real ICMP round trips
    JITTER_FRACTION: float = 0.05

    @classmethod
    def link_latency_ms(cls, weight: float, bandwidth_mbps: float) -> float:
        """Baseline one-way latency of a link: propagation plus serialization of one frame.

        Args:
            weight: Configured link weight, used as a proxy for distance.
            bandwidth_mbps: Link capacity in megabits per second.

        Returns:
            Latency in milliseconds.
        """
        serialization_ms = cls.FRAME_BITS / (max(bandwidth_mbps, 1.0) * 1000.0)
        return round(cls.PROPAGATION_MS_PER_WEIGHT * weight + serialization_ms, 3)

    def _jitter(self, latency_ms: float) -> float:
        """Apply a small random variation to a healthy latency sample."""
        spread = self._rng.uniform(-self.JITTER_FRACTION, self.JITTER_FRACTION)
        return round(latency_ms * (1 + spread), 3)

    def __init__(self, config: Any = None) -> None:
        """Initialize VirtualNetwork with initial topology state.

        Args:
            config: Optional topology configuration or Settings. If omitted,
                    loads from configuration files.
        """
        # Node state map: node_id -> {id, name, ip, status, simulated_latency_ms, simulated_loss_pct, node_type}
        self._nodes: dict[str, dict[str, Any]] = {}

        # Link state map: (src, tgt) -> {status, weight, bandwidth_mbps, latency_ms, packet_loss_pct}
        self._links: dict[tuple[str, str], dict[str, Any]] = {}

        # IP to Node ID lookup index
        self._ip_to_node: dict[str, str] = {}

        # Concurrency lock
        self._lock = asyncio.Lock()

        # Source of measurement jitter
        self._rng = random.Random()

        # Initialize network from config
        self.setup_from_config(config)

    def setup_from_config(self, config: Any = None) -> None:
        """Initialize or rebuild the simulated network from topology configuration.

        Args:
            config: Settings, NetworkConfig, raw dictionary, or None (loads from get_settings()).
        """
        nodes_raw: list[Any] = []
        links_raw: list[Any] = []

        if config is not None:
            if isinstance(config, dict):
                nodes_raw = config.get("nodes", [])
                links_raw = config.get("links", [])
            elif hasattr(config, "topology"):
                nodes_raw = config.topology.nodes
                links_raw = config.topology.links
            elif hasattr(config, "nodes"):
                nodes_raw = config.nodes
                links_raw = getattr(config, "links", [])
        else:
            try:
                settings = get_settings()
                nodes_raw = settings.topology.nodes
                links_raw = settings.topology.links
            except Exception:
                pass

        if not nodes_raw:
            # Attempt to read direct YAML fallback
            yaml_path = Path(__file__).resolve().parent.parent.parent / "config" / "network_topology.yaml"
            if yaml_path.is_file():
                try:
                    with open(yaml_path, "r", encoding="utf-8") as f:
                        data = yaml.safe_load(f)
                        if isinstance(data, dict):
                            nodes_raw = data.get("nodes", [])
                            links_raw = data.get("links", [])
                except Exception as exc:
                    logger.warning("Could not parse topology YAML: {}", exc)

        self._nodes.clear()
        self._links.clear()
        self._ip_to_node.clear()

        # Populate nodes
        for item in nodes_raw:
            if hasattr(item, "id"):
                node_id = str(item.id)
                name = getattr(item, "name", node_id)
                ip = getattr(item, "ip_address", "")
                node_type = getattr(item, "node_type", "router")
            elif isinstance(item, dict):
                node_id = str(item.get("id"))
                name = item.get("name", node_id)
                ip = item.get("ip_address", "")
                node_type = item.get("node_type", "router")
            else:
                continue

            self._nodes[node_id] = {
                "id": node_id,
                "name": name,
                "ip": ip,
                "status": NodeStatus.UP,
                "simulated_latency_ms": self.DEFAULT_NODE_LATENCY_MS,
                "simulated_loss_pct": 0.0,
                "node_type": node_type,
            }
            if ip:
                self._ip_to_node[ip] = node_id

        # Populate links (bidirectional support)
        for item in links_raw:
            if hasattr(item, "source") and hasattr(item, "target"):
                src = str(item.source)
                tgt = str(item.target)
                weight = float(getattr(item, "weight", 1.0))
                bw = float(getattr(item, "bandwidth_mbps", 100.0))
            elif isinstance(item, dict):
                src = str(item.get("source"))
                tgt = str(item.get("target"))
                weight = float(item.get("weight", 1.0))
                bw = float(item.get("bandwidth_mbps", 100.0))
            else:
                continue

            link_data = {
                "status": LinkStatus.UP,
                "weight": weight,
                "bandwidth_mbps": bw,
                "latency_ms": self.link_latency_ms(weight, bw),
                "base_latency_ms": self.link_latency_ms(weight, bw),
                "packet_loss_pct": 0.0,
            }
            self._links[(src, tgt)] = dict(link_data)
            self._links[(tgt, src)] = dict(link_data)

        logger.info(
            "VirtualNetwork initialized with {} simulated nodes and {} links.",
            len(self._nodes),
            len(self._links) // 2,
        )

    def get_node_response(self, node_id_or_ip: str) -> SimulatedResponse:
        """Return simulated ping probe response for a given node identifier or IP.

        Args:
            node_id_or_ip: Node identifier (e.g. 'router-a') or IP (e.g. '192.168.1.1').

        Returns:
            SimulatedResponse indicating reachability, RTT latency, and loss.
        """
        # Resolve by ID or by indexed IP address
        node_id = node_id_or_ip
        if node_id not in self._nodes and node_id_or_ip in self._ip_to_node:
            node_id = self._ip_to_node[node_id_or_ip]

        node_data = self._nodes.get(node_id)
        if not node_data:
            return SimulatedResponse(
                reachable=False,
                latency_ms=0.0,
                packet_loss_pct=100.0,
                status="unknown",
                details={"error": f"Node '{node_id_or_ip}' not found in virtual network"},
            )

        status = node_data["status"]
        status_val = status.value if hasattr(status, "value") else str(status)

        if status_val == NodeStatus.DOWN.value:
            return SimulatedResponse(
                reachable=False,
                latency_ms=0.0,
                packet_loss_pct=100.0,
                status=status_val,
                details={"node_id": node_id, "ip": node_data["ip"]},
            )

        if status_val == NodeStatus.DEGRADED.value:
            return SimulatedResponse(
                reachable=True,
                latency_ms=node_data["simulated_latency_ms"],
                packet_loss_pct=node_data["simulated_loss_pct"],
                status=status_val,
                details={"node_id": node_id, "ip": node_data["ip"]},
            )

        # Node is UP
        return SimulatedResponse(
            reachable=True,
            latency_ms=self._jitter(node_data["simulated_latency_ms"]),
            packet_loss_pct=node_data["simulated_loss_pct"],
            status=status_val,
            details={"node_id": node_id, "ip": node_data["ip"]},
        )

    def get_link_response(self, source: str, target: str) -> SimulatedResponse:
        """Return simulated probe response for a communication link between two nodes.

        Args:
            source: Source node identifier.
            target: Destination node identifier.

        Returns:
            SimulatedResponse indicating whether the link is forwarding traffic.
        """
        link_data = self._links.get((source, target)) or self._links.get((target, source))
        if not link_data:
            return SimulatedResponse(
                reachable=False,
                latency_ms=0.0,
                packet_loss_pct=100.0,
                status="unknown",
                details={"error": f"Link between '{source}' and '{target}' not found"},
            )

        status = link_data["status"]
        status_val = status.value if hasattr(status, "value") else str(status)

        if status_val == LinkStatus.DOWN.value:
            return SimulatedResponse(
                reachable=False,
                latency_ms=0.0,
                packet_loss_pct=100.0,
                status=status_val,
                details={"source": source, "target": target},
            )

        latency = link_data.get("latency_ms", self.DEFAULT_LINK_LATENCY_MS)
        return SimulatedResponse(
            reachable=True,
            latency_ms=self._jitter(latency) if status_val == LinkStatus.UP.value else latency,
            packet_loss_pct=link_data.get("packet_loss_pct", 0.0),
            status=status_val,
            details={"source": source, "target": target},
        )

    def set_node_status(self, node_id: str, status: NodeStatus | str) -> None:
        """Update operational state (UP, DOWN, DEGRADED) for a simulated node.

        Args:
            node_id: Target node identifier.
            status: New operational status.
        """
        if node_id in self._nodes:
            norm_status = (
                status
                if isinstance(status, NodeStatus)
                else NodeStatus(str(status).lower())
            )
            self._nodes[node_id]["status"] = norm_status
            logger.info("VirtualNetwork: node '{}' status set to {}", node_id, norm_status)
        else:
            logger.warning("VirtualNetwork: cannot set status on unknown node '{}'", node_id)

    def set_link_status(
        self, source: str, target: str, status: LinkStatus | str
    ) -> None:
        """Update operational state for a simulated link (bidirectional).

        Args:
            source: Source node identifier.
            target: Target node identifier.
            status: New LinkStatus.
        """
        norm_status = (
            status
            if isinstance(status, LinkStatus)
            else LinkStatus(str(status).lower())
        )
        updated = False
        for pair in [(source, target), (target, source)]:
            if pair in self._links:
                self._links[pair]["status"] = norm_status
                updated = True

        if updated:
            logger.info(
                "VirtualNetwork: link '{}' <-> '{}' status set to {}",
                source,
                target,
                norm_status,
            )
        else:
            logger.warning(
                "VirtualNetwork: link '{}' <-> '{}' not found to update status",
                source,
                target,
            )

    def inject_latency(self, node_id: str, latency_ms: float) -> None:
        """Inject elevated latency into a simulated node.

        Args:
            node_id: Target node ID.
            latency_ms: High latency in milliseconds.
        """
        if node_id in self._nodes:
            self._nodes[node_id]["simulated_latency_ms"] = float(latency_ms)
            if float(latency_ms) > 100.0:
                self._nodes[node_id]["status"] = NodeStatus.DEGRADED
            logger.info(
                "VirtualNetwork: injected latency {}ms onto node '{}'",
                latency_ms,
                node_id,
            )

    def inject_packet_loss(self, node_id: str, loss_pct: float) -> None:
        """Inject packet loss percentage into a simulated node.

        Args:
            node_id: Target node ID.
            loss_pct: Packet loss percentage (0.0 - 100.0).
        """
        if node_id in self._nodes:
            self._nodes[node_id]["simulated_loss_pct"] = float(loss_pct)
            if float(loss_pct) > 5.0:
                self._nodes[node_id]["status"] = NodeStatus.DEGRADED
            logger.info(
                "VirtualNetwork: injected packet loss {}% onto node '{}'",
                loss_pct,
                node_id,
            )

    def reset(self) -> None:
        """Restore all nodes and links to healthy defaults."""
        for node_id, data in self._nodes.items():
            data["status"] = NodeStatus.UP
            data["simulated_latency_ms"] = self.DEFAULT_NODE_LATENCY_MS
            data["simulated_loss_pct"] = 0.0

        for pair, data in self._links.items():
            data["status"] = LinkStatus.UP
            data["latency_ms"] = data.get("base_latency_ms", self.DEFAULT_LINK_LATENCY_MS)
            data["packet_loss_pct"] = 0.0

        logger.info("VirtualNetwork: all simulated nodes and links reset to healthy defaults.")

    def sync_topology(self, nodes: list[dict[str, Any]], links: list[dict[str, Any]]) -> None:
        """Match the simulated network to an edited topology.

        Devices and links that still exist keep their current state (an injected fault
        stays injected); new ones start healthy and removed ones are dropped.

        Args:
            nodes: Dicts with id, name, ip_address and node_type.
            links: Dicts with source, target, weight and bandwidth_mbps.
        """
        wanted_nodes = {str(n["id"]) for n in nodes}
        for node_id in list(self._nodes):
            if node_id not in wanted_nodes:
                del self._nodes[node_id]
        for n in nodes:
            node_id = str(n["id"])
            current = self._nodes.get(node_id)
            if current is None:
                self._nodes[node_id] = {
                    "id": node_id,
                    "status": NodeStatus.UP,
                    "simulated_latency_ms": self.DEFAULT_NODE_LATENCY_MS,
                    "simulated_loss_pct": 0.0,
                }
                current = self._nodes[node_id]
            current.update(
                name=n.get("name", node_id),
                ip=n.get("ip_address", ""),
                node_type=n.get("node_type", "router"),
            )
        self._ip_to_node = {
            data["ip"]: node_id for node_id, data in self._nodes.items() if data.get("ip")
        }

        wanted_links: set[tuple[str, str]] = set()
        for link in links:
            src, tgt = str(link["source"]), str(link["target"])
            weight = float(link.get("weight", 1.0))
            bw = float(link.get("bandwidth_mbps", 100.0))
            base = self.link_latency_ms(weight, bw)
            for pair in ((src, tgt), (tgt, src)):
                wanted_links.add(pair)
                current = self._links.get(pair)
                if current is None:
                    self._links[pair] = {
                        "status": LinkStatus.UP,
                        "latency_ms": base,
                        "packet_loss_pct": 0.0,
                    }
                    current = self._links[pair]
                elif current.get("base_latency_ms") != base and current["status"] == LinkStatus.UP:
                    current["latency_ms"] = base
                current.update(weight=weight, bandwidth_mbps=bw, base_latency_ms=base)
        for pair in list(self._links):
            if pair not in wanted_links:
                del self._links[pair]

    def get_all_nodes(self) -> dict[str, dict[str, Any]]:
        """Return a snapshot of all node simulation states."""
        return {k: dict(v) for k, v in self._nodes.items()}

    def get_all_links(self) -> dict[tuple[str, str], dict[str, Any]]:
        """Return a snapshot of all link simulation states."""
        return {k: dict(v) for k, v in self._links.items()}


__all__ = ["VirtualNetwork", "SimulatedResponse"]
