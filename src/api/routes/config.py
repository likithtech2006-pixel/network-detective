"""System Configuration API routes.

Provides endpoints to view and dynamically update runtime operational parameters,
including polling frequencies, detection thresholds, and autonomous healing flags.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, HTTPException, Request
from loguru import logger

from src.core.config import get_settings
from src.detector.threshold_engine import ThresholdEngine

router = APIRouter(prefix="/api/config", tags=["Configuration"])


def _build_config_dict(request: Request) -> dict[str, Any]:
    """Construct a consolidated dictionary of active configuration settings."""
    settings = get_settings()
    th = settings.thresholds
    state = request.app.state

    return {
        "app_name": settings.app_name,
        "environment": settings.environment,
        # How often the health monitor probes in the current network mode
        "polling_interval_sec": state.health_monitor.interval_sec,
        "network_mode": state.health_monitor.mode,
        "thresholds": {
            "latency_warn_ms": th.latency_warn_ms,
            "latency_critical_ms": th.latency_critical_ms,
            "packet_loss_warn_pct": th.packet_loss_warn_pct,
            "packet_loss_critical_pct": th.packet_loss_critical_pct,
            "ping_timeout_sec": th.ping_timeout_sec,
            "max_retries": th.max_retries,
        },
        # Flattened aliases for frontend dashboard client compatibility
        "latency_warning_ms": th.latency_warn_ms,
        "latency_critical_ms": th.latency_critical_ms,
        "packet_loss_warning_pct": th.packet_loss_warn_pct,
        "packet_loss_critical_pct": th.packet_loss_critical_pct,
        "healing_enabled": state.self_healer.enabled,
        "auto_rollback": state.incident_resolver.rollback_on_failure,
    }


@router.get("", summary="Get system configuration")
@router.get("/", summary="Get system configuration", include_in_schema=False)
async def get_config(request: Request) -> dict[str, Any]:
    """Retrieve active system operational parameters and fault detection thresholds."""
    return _build_config_dict(request)


@router.put("", summary="Update system configuration")
@router.put("/", summary="Update system configuration", include_in_schema=False)
async def update_config(
    request: Request,
    payload: dict[str, Any] = Body(...),
) -> dict[str, Any]:
    """Change thresholds, the probe interval and the healing switches without a restart."""
    settings = get_settings()
    state = request.app.state
    monitor = state.health_monitor

    # 1. Probe interval for the current network mode
    if payload.get("polling_interval_sec") is not None:
        new_interval = float(payload["polling_interval_sec"])
        if not 0.2 <= new_interval <= 60:
            raise HTTPException(status_code=400, detail="Probe interval must be 0.2 to 60 seconds")
        monitor.interval_sec = new_interval
        if monitor.mode == "live":
            monitor.live_interval_sec = new_interval
        else:
            monitor.sim_interval_sec = new_interval
        logger.info("Health monitor now probes every {}s", new_interval)

    if payload.get("healing_enabled") is not None:
        state.self_healer.enabled = bool(payload["healing_enabled"])
        logger.info("Self-healing enabled: {}", state.self_healer.enabled)
    if payload.get("auto_rollback") is not None:
        state.incident_resolver.rollback_on_failure = bool(payload["auto_rollback"])
        logger.info(
            "Rollback on failed verification: {}", state.incident_resolver.rollback_on_failure
        )

    # 2. Update Thresholds from nested dictionary
    th = settings.thresholds
    nested_th = payload.get("thresholds")
    if isinstance(nested_th, dict):
        for k, v in nested_th.items():
            if hasattr(th, k) and v is not None:
                setattr(th, k, float(v) if isinstance(v, (int, float)) else v)
                logger.info("Updated threshold {}: {}", k, v)

    # 3. Update Thresholds from direct flattened keys
    flat_mappings = {
        "latency_warning_ms": "latency_warn_ms",
        "latency_warn_ms": "latency_warn_ms",
        "latency_critical_ms": "latency_critical_ms",
        "packet_loss_warning_pct": "packet_loss_warn_pct",
        "packet_loss_warn_pct": "packet_loss_warn_pct",
        "packet_loss_critical_pct": "packet_loss_critical_pct",
        "ping_timeout_sec": "ping_timeout_sec",
        "max_retries": "max_retries",
    }

    for flat_key, model_attr in flat_mappings.items():
        if flat_key in payload and payload[flat_key] is not None:
            val = payload[flat_key]
            setattr(th, model_attr, int(val) if model_attr == "max_retries" else float(val))
            logger.info("Updated threshold {} -> {}", model_attr, val)

    # The running monitor copied the thresholds at startup; give it the new ones
    monitor.threshold_engine = ThresholdEngine()
    monitor.confirmations = max(1, int(th.max_retries))

    return _build_config_dict(request)
