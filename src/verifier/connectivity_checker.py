"""Connectivity verification engine for hop-by-hop and end-to-end path validation."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from src.utils.helpers import ping_host
from src.utils.logger import logger


@dataclass
class PathCheckResult:
    """Detailed reachability and latency breakdown for an entire network path."""

    path: list[str]
    all_reachable: bool
    hop_results: list[dict[str, Any]]
    end_to_end_latency_ms: float | None
    total_latency_ms: float = 0.0
    packet_loss_pct: float = 0.0
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize PathCheckResult to dictionary."""
        return {
            "path": self.path,
            "all_reachable": self.all_reachable,
            "hop_results": self.hop_results,
            "end_to_end_latency_ms": self.end_to_end_latency_ms,
            "total_latency_ms": self.total_latency_ms,
            "packet_loss_pct": self.packet_loss_pct,
            "details": self.details,
        }


class ConnectivityChecker:
    """Verifies reachability and measures RTT along alternate or restored network routes.

    Supports probing live infrastructure via ICMP ping as well as querying
    in-memory simulated network topologies.
    """

    def __init__(self, virtual_network: Any = None) -> None:
        """Initialize ConnectivityChecker.

        Args:
            virtual_network: Optional VirtualNetwork instance for simulated environments.
        """
        self.virtual_network = virtual_network

    async def check_path_connectivity(
        self,
        path: list[str],
        node_ips: dict[str, str] | None = None,
        timeout: float = 3.0,
    ) -> PathCheckResult:
        """Verify that every intermediate node and hop in a path is operational.

        Iterates through the path, verifying each node's reachability. In virtual
        mode, checks node and link states directly; in live mode, issues ICMP pings.

        Args:
            path: Ordered list of node identifiers (e.g. ['router-a', 'switch-c', 'server-d']).
            node_ips: Optional mapping of node ID to IP address.
            timeout: Maximum timeout in seconds per probe.

        Returns:
            PathCheckResult containing overall reachability, latency, and per-hop status.
        """
        if not path:
            return PathCheckResult(
                path=[],
                all_reachable=False,
                hop_results=[],
                end_to_end_latency_ms=None,
                total_latency_ms=0.0,
                packet_loss_pct=100.0,
                details={"error": "Empty path provided for connectivity check"},
            )

        ips = node_ips or {}
        hop_results: list[dict[str, Any]] = []
        total_latency = 0.0
        failed_hops = 0

        # Check virtual network if available
        if self.virtual_network is not None:
            return await self._check_virtual_path(path)

        # Live probe mode using ping_host
        for node in path:
            ip = ips.get(node, node)
            reachable, rtt = await ping_host(ip, timeout=timeout)
            latency = rtt if rtt is not None else 0.0

            if reachable:
                total_latency += latency
            else:
                failed_hops += 1

            hop_results.append(
                {
                    "node": node,
                    "ip": ip,
                    "reachable": reachable,
                    "latency_ms": latency,
                }
            )

        all_reachable = failed_hops == 0
        packet_loss_pct = (failed_hops / len(path)) * 100.0 if path else 100.0
        end_to_end_latency = round(total_latency, 2) if all_reachable else None

        logger.debug(
            "Path check for {}: all_reachable={}, e2e_latency={}ms, loss={}%",
            " -> ".join(path),
            all_reachable,
            end_to_end_latency,
            packet_loss_pct,
        )

        return PathCheckResult(
            path=list(path),
            all_reachable=all_reachable,
            hop_results=hop_results,
            end_to_end_latency_ms=end_to_end_latency,
            total_latency_ms=round(total_latency, 2),
            packet_loss_pct=round(packet_loss_pct, 1),
            details={
                "failed_hops": failed_hops,
                "total_hops": len(path),
            },
        )

    async def check_end_to_end(
        self,
        source_ip: str,
        target_ip: str,
        timeout: float = 3.0,
    ) -> tuple[bool, float | None]:
        """Perform a single end-to-end reachability check to destination IP.

        Args:
            source_ip: Source IPv4 or IPv6 address.
            target_ip: Destination IPv4 or IPv6 address to ping.
            timeout: Ping timeout in seconds.

        Returns:
            Tuple of (reachable: bool, latency_ms: float | None).
        """
        if self.virtual_network is not None:
            # Check virtual destination
            resp = self.virtual_network.get_node_response(target_ip)
            return resp.reachable, resp.latency_ms if resp.reachable else None

        return await ping_host(target_ip, timeout=timeout)

    async def _check_virtual_path(self, path: list[str]) -> PathCheckResult:
        """Internal evaluator using in-memory VirtualNetwork state."""
        hop_results: list[dict[str, Any]] = []
        total_latency = 0.0
        all_reachable = True
        accumulated_loss = 0.0

        for node in path:
            resp = self.virtual_network.get_node_response(node)
            reachable = resp.reachable
            latency = resp.latency_ms

            if not reachable:
                all_reachable = False

            total_latency += latency
            accumulated_loss = max(accumulated_loss, resp.packet_loss_pct)

            hop_results.append(
                {
                    "node": node,
                    "reachable": reachable,
                    "latency_ms": latency,
                    "packet_loss_pct": resp.packet_loss_pct,
                    "status": resp.status,
                }
            )

        # Also inspect links between adjacent hops
        for u, v in zip(path[:-1], path[1:]):
            link_resp = self.virtual_network.get_link_response(u, v)
            if not link_resp.reachable:
                all_reachable = False
            total_latency += link_resp.latency_ms
            accumulated_loss = max(accumulated_loss, link_resp.packet_loss_pct)

        e2e_latency = round(total_latency, 2) if all_reachable else None

        return PathCheckResult(
            path=list(path),
            all_reachable=all_reachable,
            hop_results=hop_results,
            end_to_end_latency_ms=e2e_latency,
            total_latency_ms=round(total_latency, 2),
            packet_loss_pct=round(accumulated_loss, 1),
            details={"mode": "virtual_network"},
        )


__all__ = ["ConnectivityChecker", "PathCheckResult"]
