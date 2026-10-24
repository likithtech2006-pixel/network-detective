"""Network mode API: switch between simulation and live probing, and help add real devices."""

from __future__ import annotations

import asyncio
import platform
import re
import socket
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from src.api.schemas import NetworkModeRequest, PingRequest
from src.monitor.live_probe import LiveProber
from src.monitor.topology_service import TopologyError, TopologyService

router = APIRouter(prefix="/api/network", tags=["Network"])

_prober = LiveProber(timeout_sec=1.0)


def _service(request: Request) -> TopologyService:
    return request.app.state.topology_service


@router.get("/mode", summary="Get the network mode")
async def get_mode(request: Request) -> dict[str, Any]:
    """Return whether the monitor probes the simulation or pings real devices."""
    monitor = request.app.state.health_monitor
    return {"mode": monitor.mode, "interval_sec": monitor.interval_sec}


@router.put("/mode", summary="Switch the network mode")
async def set_mode(req: NetworkModeRequest, request: Request) -> dict[str, Any]:
    """Switch modes. All devices start healthy again and open incidents are closed."""
    try:
        await _service(request).set_mode(req.mode)
    except TopologyError as err:
        raise HTTPException(status_code=err.status_code, detail=str(err)) from err
    return await get_mode(request)


@router.post("/ping", summary="Ping an address once")
async def ping(req: PingRequest) -> dict[str, Any]:
    """Send one real ICMP echo request, e.g. to test an address before adding it."""
    sample = await _prober.ping(req.address.strip())
    return {
        "address": req.address.strip(),
        "reachable": sample.reachable,
        "latency_ms": sample.latency_ms if sample.reachable else None,
    }


async def _default_gateway() -> str | None:
    """Find this computer's default gateway (usually the Wi-Fi or LAN router)."""
    if platform.system() == "Darwin":
        cmd, pattern = ["route", "-n", "get", "default"], r"gateway:\s*(\S+)"
    elif platform.system() == "Linux":
        cmd, pattern = ["ip", "route", "show", "default"], r"default via (\S+)"
    else:
        return None
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL
        )
        out, _ = await asyncio.wait_for(proc.communicate(), timeout=2)
    except (OSError, TimeoutError):
        return None
    match = re.search(pattern, out.decode(errors="ignore"))
    return match.group(1) if match else None


def _local_ip() -> str | None:
    """Find this computer's address on the local network (no packets are sent)."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except OSError:
        return None


@router.get("/suggestions", summary="Suggest real devices to monitor")
async def suggestions() -> list[dict[str, str]]:
    """Devices that are reachable from this computer and useful for a live demo."""
    found: list[dict[str, str]] = []
    gateway = await _default_gateway()
    if gateway:
        found.append({"name": "Home Router", "node_type": "router", "ip_address": gateway,
                      "description": "Your default gateway (Wi-Fi or LAN router)"})
    local = _local_ip()
    if local:
        found.append({"name": "This Computer", "node_type": "server", "ip_address": local,
                      "description": "The machine running Network Detective"})
    found.append({"name": "Google DNS", "node_type": "server", "ip_address": "8.8.8.8",
                  "description": "Public DNS server on the internet"})
    found.append({"name": "Cloudflare DNS", "node_type": "server", "ip_address": "1.1.1.1",
                  "description": "Public DNS server on the internet"})
    return found
