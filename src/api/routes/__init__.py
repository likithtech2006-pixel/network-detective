"""API routes package.

Exports individual route modules and aggregates system status endpoints.
"""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter()


@router.get("/health", tags=["System"])
@router.get("/api/health", tags=["System"], include_in_schema=False)
async def health_check() -> dict[str, str]:
    """Basic health check endpoint returning system status."""
    return {"status": "ok", "service": "network-detective"}


@router.get("/status", tags=["System"])
@router.get("/api/status", tags=["System"], include_in_schema=False)
async def status_check() -> dict[str, str]:
    """Extended status endpoint."""
    return {"status": "operational", "version": "0.1.0"}
