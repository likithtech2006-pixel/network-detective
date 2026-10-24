"""System Configuration API routes.

Provides endpoints to view and dynamically update runtime operational parameters,
including polling frequencies, detection thresholds, and autonomous healing flags.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body
from loguru import logger

from src.api.schemas import ConfigUpdateRequest
from src.core.config import get_settings

router = APIRouter(prefix="/api/config", tags=["Configuration"])


def _build_config_dict() -> dict[str, Any]:
    """Construct a consolidated dictionary of active configuration settings."""
    settings = get_settings()
    th = settings.thresholds

    return {
        "app_name": settings.app_name,
        "environment": settings.environment,
        "polling_interval_sec": settings.polling_interval_sec,
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
        "healing_enabled": True,
        "auto_rollback": True,
    }


@router.get("", summary="Get system configuration")
@router.get("/", summary="Get system configuration", include_in_schema=False)
async def get_config() -> dict[str, Any]:
    """Retrieve active system operational parameters and fault detection thresholds."""
    return _build_config_dict()


@router.put("", summary="Update system configuration")
@router.put("/", summary="Update system configuration", include_in_schema=False)
async def update_config(
    payload: dict[str, Any] = Body(...),
) -> dict[str, Any]:
    """Dynamically modify runtime thresholds or polling intervals without restart."""
    settings = get_settings()

    # 1. Update Polling Interval
    if "polling_interval_sec" in payload and payload["polling_interval_sec"] is not None:
        new_interval = int(payload["polling_interval_sec"])
        if 1 <= new_interval <= 3600:
            settings.polling_interval_sec = new_interval
            logger.info("Updated polling_interval_sec to {}", new_interval)

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

    return _build_config_dict()
