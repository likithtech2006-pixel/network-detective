"""Real ICMP probing of devices for live mode."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

import ping3

from src.utils.logger import logger


@dataclass
class ProbeSample:
    """One probe result, shaped like the simulated network's responses."""

    reachable: bool
    latency_ms: float
    packet_loss_pct: float
    status: str


class LiveProber:
    """Sends one ICMP echo request to each device, all in parallel."""

    def __init__(self, timeout_sec: float = 1.0) -> None:
        """Initialize the prober.

        Args:
            timeout_sec: How long to wait for each echo reply.
        """
        self.timeout_sec = timeout_sec
        self._warned: set[str] = set()

    async def ping(self, host: str) -> ProbeSample:
        """Ping one host and report reachability and round-trip time.

        Args:
            host: IP address or hostname.

        Returns:
            ProbeSample; an unreachable host has 100% loss and latency 0.
        """
        try:
            rtt = await asyncio.to_thread(ping3.ping, host, timeout=self.timeout_sec, unit="ms")
        except Exception as exc:
            # e.g. raw sockets not permitted, or an unresolvable hostname
            if host not in self._warned:
                self._warned.add(host)
                logger.warning("Live ping to {} failed: {}", host, exc)
            rtt = None
        # ping3 returns None on timeout and False on errors; bool is a subclass of int
        if isinstance(rtt, float):
            return ProbeSample(True, round(rtt, 3), 0.0, "up")
        return ProbeSample(False, 0.0, 100.0, "down")

    async def ping_many(self, hosts: dict[str, str]) -> dict[str, ProbeSample]:
        """Ping several devices at once.

        Args:
            hosts: Device ID -> IP address or hostname.

        Returns:
            Device ID -> ProbeSample.
        """
        ids = list(hosts)
        results = await asyncio.gather(*(self.ping(hosts[i]) for i in ids))
        return dict(zip(ids, results, strict=True))


__all__ = ["LiveProber", "ProbeSample"]
