"""Network probing and formatting utility helpers."""

from __future__ import annotations

import asyncio
import re
import sys
import time
from datetime import datetime, timezone

from loguru import logger


def timestamp_now() -> datetime:
    """Return the current timezone-aware UTC datetime.

    Returns:
        datetime object in UTC.
    """
    return datetime.now(timezone.utc)


def format_path(path: list[str]) -> str:
    """Format a list of node identifiers into an arrow-delimited route string.

    Args:
        path: List of node names (e.g. ['router-a', 'router-b', 'server-d']).

    Returns:
        Formatted string (e.g. 'router-a → router-b → server-d') or empty string.
    """
    if not path:
        return ""
    return " → ".join(str(step) for step in path)


async def ping_host(host: str, timeout: float = 3.0) -> tuple[bool, float | None]:
    """Ping a host using ICMP and measure Round-Trip Time (RTT).

    First attempts ping3 library; if raw socket creation lacks root permissions,
    gracefully falls back to system ping utility asynchronously.

    Args:
        host: Hostname or IPv4/IPv6 address to ping.
        timeout: Maximum duration to wait for response in seconds.

    Returns:
        Tuple of (reachable: bool, rtt_ms: float | None).
    """
    # 1. Try ping3 via thread pool executor
    try:
        import ping3

        def _do_ping3() -> float | None | bool:
            return ping3.ping(host, timeout=timeout, unit="ms")

        result = await asyncio.to_thread(_do_ping3)
        if isinstance(result, (int, float)) and result is not False:
            return True, round(float(result), 2)
        if result is None or result is False:
            return False, None
    except PermissionError:
        logger.trace("ICMP raw socket permission denied; falling back to system ping for {}", host)
    except Exception as exc:
        logger.trace("ping3 probe failed for {}: {}", host, exc)

    # 2. System ping fallback
    return await _system_ping(host, timeout)


async def _system_ping(host: str, timeout: float = 3.0) -> tuple[bool, float | None]:
    """Perform ICMP probe via OS ping command."""
    is_windows = sys.platform == "win32"
    is_darwin = sys.platform == "darwin"

    if is_windows:
        cmd = ["ping", "-n", "1", "-w", str(int(timeout * 1000)), host]
    elif is_darwin:
        # macOS ping uses -t for timeout in seconds
        cmd = ["ping", "-c", "1", "-t", str(max(1, int(timeout))), host]
    else:
        # Linux ping uses -W for timeout in seconds
        cmd = ["ping", "-c", "1", "-W", str(max(1, int(timeout))), host]

    start_time = time.perf_counter()
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout + 1.0)
        elapsed_ms = (time.perf_counter() - start_time) * 1000.0

        if proc.returncode == 0:
            out_str = stdout.decode("utf-8", errors="ignore")
            # Parse round-trip time if available (e.g., time=12.4 ms)
            match = re.search(r"time[=<]([0-9.]+)\s*ms", out_str, re.IGNORECASE)
            if match:
                return True, round(float(match.group(1)), 2)
            return True, round(elapsed_ms, 2)
        return False, None
    except (asyncio.TimeoutError, OSError):
        return False, None


async def tcp_check(host: str, port: int, timeout: float = 3.0) -> bool:
    """Check TCP connectivity to a specific host and port.

    Args:
        host: Target IP or domain.
        port: Target TCP port.
        timeout: Connection timeout in seconds.

    Returns:
        True if connection succeeded; False otherwise.
    """
    try:
        _, writer = await asyncio.wait_for(
            asyncio.open_connection(host=host, port=port),
            timeout=timeout,
        )
        writer.close()
        await writer.wait_closed()
        return True
    except (OSError, asyncio.TimeoutError):
        return False


__all__ = [
    "timestamp_now",
    "format_path",
    "ping_host",
    "tcp_check",
]
