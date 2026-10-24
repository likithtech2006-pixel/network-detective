"""ICMP ping probe implementation for measuring latency, loss, and jitter."""

from __future__ import annotations

import asyncio
import statistics
from dataclasses import asdict, dataclass
from typing import Any

from src.utils.helpers import ping_host
from src.utils.logger import logger


@dataclass
class PingResult:
    """Telemetry results from an ICMP ping probe."""

    host: str
    reachable: bool
    avg_latency_ms: float | None
    packet_loss_pct: float
    min_latency_ms: float | None
    max_latency_ms: float | None
    jitter_ms: float

    def to_dict(self) -> dict[str, Any]:
        """Convert dataclass fields to a standard dictionary."""
        return asdict(self)


class PingProbe:
    """ICMP ping prober with multi-sample statistics and fallback support."""

    def __init__(self, default_timeout: float = 3.0, default_count: int = 3) -> None:
        """Initialize PingProbe.

        Args:
            default_timeout: Maximum seconds to wait per ICMP echo reply.
            default_count: Number of echo packets sent per probe cycle.
        """
        self.default_timeout = default_timeout
        self.default_count = max(1, default_count)

    async def _ping_single(self, host: str, timeout: float) -> tuple[bool, float | None]:
        """Execute a single ICMP probe using ping3 with system ping fallback.

        Args:
            host: Target hostname or IP address.
            timeout: Probe timeout in seconds.

        Returns:
            Tuple of (reachable, rtt_ms).
        """
        try:
            import ping3

            def _do_ping() -> float | None | bool:
                # ping3.ping returns seconds by default or ms when unit='ms'
                return ping3.ping(host, timeout=timeout, unit="ms")

            res = await asyncio.to_thread(_do_ping)
            if isinstance(res, (int, float)) and res is not False:
                return True, round(float(res), 2)
            if res is False or res is None:
                # Might be timeout or unprivileged socket; try fallback helper
                return await ping_host(host, timeout=timeout)
        except PermissionError:
            logger.trace("ping3 socket permission denied for {}; invoking system ping helper", host)
            return await ping_host(host, timeout=timeout)
        except Exception as exc:
            logger.trace("ping3 error for {}: {}; attempting fallback helper", host, exc)
            return await ping_host(host, timeout=timeout)

        return await ping_host(host, timeout=timeout)

    async def probe(
        self,
        host: str,
        timeout: float | None = None,
        count: int | None = None,
    ) -> PingResult:
        """Send a sequence of ping probes and calculate aggregated network metrics.

        Args:
            host: Target IP or domain to probe.
            timeout: Ping timeout per packet in seconds.
            count: Number of echo request packets to send.

        Returns:
            PingResult containing reachability, avg/min/max latency, loss, and jitter.
        """
        t = timeout if timeout is not None else self.default_timeout
        c = max(1, count if count is not None else self.default_count)

        latencies: list[float] = []
        lost_count = 0

        for idx in range(c):
            try:
                ok, lat = await self._ping_single(host, t)
                if ok and lat is not None:
                    latencies.append(lat)
                else:
                    lost_count += 1
            except Exception as err:
                logger.debug("Exception during ping probe to {} (pkt {}/{}): {}", host, idx + 1, c, err)
                lost_count += 1

            # Brief interval between successive packets
            if idx < c - 1:
                await asyncio.sleep(0.05)

        total_sent = len(latencies) + lost_count
        packet_loss_pct = round((lost_count / total_sent) * 100.0, 2) if total_sent > 0 else 100.0
        reachable = len(latencies) > 0

        if reachable:
            min_latency_ms = round(min(latencies), 2)
            max_latency_ms = round(max(latencies), 2)
            avg_latency_ms = round(statistics.mean(latencies), 2)

            # Jitter: mean absolute deviation between consecutive packet latencies
            if len(latencies) >= 2:
                diffs = [abs(latencies[i] - latencies[i - 1]) for i in range(1, len(latencies))]
                jitter_ms = round(statistics.mean(diffs), 2)
            else:
                jitter_ms = 0.0
        else:
            min_latency_ms = None
            max_latency_ms = None
            avg_latency_ms = None
            jitter_ms = 0.0

        return PingResult(
            host=host,
            reachable=reachable,
            avg_latency_ms=avg_latency_ms,
            packet_loss_pct=packet_loss_pct,
            min_latency_ms=min_latency_ms,
            max_latency_ms=max_latency_ms,
            jitter_ms=jitter_ms,
        )
