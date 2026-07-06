"""Health probes — liveness and database/PostGIS readiness."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from src.core.config import get_settings
from src.db.health import get_database_health

SERVICE_NAME = "simulator-backend"

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict[str, str]:
    settings = get_settings()
    return {
        "status": "ok",
        "service": SERVICE_NAME,
        "environment": settings.ENVIRONMENT,
    }


@router.get("/health/db")
def health_db() -> dict[str, Any]:
    return get_database_health()


__all__ = ["SERVICE_NAME", "router"]
