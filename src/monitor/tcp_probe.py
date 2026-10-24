"""TCP port probe implementation for checking service connectivity and response times."""

from __future__ import annotations

import asyncio
import time
from dataclasses import asdict, dataclass
from typing import Any

from src.utils.logger import logger


@dataclass
class TcpResult:
    """Telemetry result of a TCP connectivity probe against a host and port."""

    host: str
    port: int
    reachable: bool
    response_time_ms: float | None

    def to_dict(self) -> dict[str, Any]:
        """Convert dataclass fields to a standard dictionary."""
        return asdict(self)


class TcpProbe:
    """TCP port scanner and latency prober."""

    COMMON_PORTS: dict[int, str] = {
        22: "SSH",
        80: "HTTP",
        443: "HTTPS",
        53: "DNS",
    }

    def __init__(self, default_timeout: float = 3.0) -> None:
        """Initialize TcpProbe with configurable default timeout.

        Args:
            default_timeout: Connection attempt timeout in seconds.
        """
        self.default_timeout = default_timeout

    async def probe(
        self,
        host: str,
        port: int,
        timeout: float | None = None,
    ) -> TcpResult:
        """Attempt TCP handshake to target host and port to measure reachability and latency.

        Args:
            host: Target hostname or IP address.
            port: Target TCP port number.
            timeout: Maximum handshake wait time in seconds.

        Returns:
            TcpResult containing reachability and connection handshake duration in ms.
        """
        t = timeout if timeout is not None else self.default_timeout
        start_time = time.perf_counter()

        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(host=host, port=port),
                timeout=t,
            )
            elapsed_ms = round((time.perf_counter() - start_time) * 1000.0, 2)
            try:
                close_res = writer.close()
                if asyncio.iscoroutine(close_res):
                    await close_res
                wait_closed = getattr(writer, "wait_closed", None)
                if wait_closed and callable(wait_closed):
                    res = wait_closed()
                    if asyncio.iscoroutine(res):
                        await res
            except Exception:
                pass

            return TcpResult(
                host=host,
                port=port,
                reachable=True,
                response_time_ms=elapsed_ms,
            )
        except (asyncio.TimeoutError, OSError) as exc:
            logger.trace("TCP probe failed for {}:{} - {}", host, port, exc)
            return TcpResult(
                host=host,
                port=port,
                reachable=False,
                response_time_ms=None,
            )
        except Exception as exc:
            logger.debug("Unexpected error during TCP probe for {}:{} - {}", host, port, exc)
            return TcpResult(
                host=host,
                port=port,
                reachable=False,
                response_time_ms=None,
            )

    async def probe_common_ports(
        self,
        host: str,
        ports: dict[int, str] | None = None,
        timeout: float | None = None,
    ) -> dict[int, TcpResult]:
        """Probe all standard network ports concurrently for the specified host.

        Args:
            host: Target IP or domain.
            ports: Optional mapping of port to service label. Defaults to COMMON_PORTS.
            timeout: Timeout per connection attempt in seconds.

        Returns:
            Dictionary mapping port number to TcpResult.
        """
        target_ports = ports or self.COMMON_PORTS
        tasks = [
            self.probe(host=host, port=port, timeout=timeout)
            for port in target_ports.keys()
        ]
        results = await asyncio.gather(*tasks)
        return {res.port: res for res in results}
