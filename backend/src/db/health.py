"""Database / PostGIS health probes.

These helpers must never raise out of process: callers (including the
FastAPI health route) rely on them returning structured status dicts even
when the database is unreachable
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from src.db.session import SessionLocal

logger = logging.getLogger(__name__)


def check_database_connection() -> dict[str, Any]:
    """Run ``SELECT 1`` and return a structured status dict"""
    try:
        session = SessionLocal()
    except Exception as exc:  # pragma: no cover; defensive
        logger.exception("Failed to open database session")
        return {"status": "error", "message": str(exc)}
    try:
        result = session.execute(text("SELECT 1")).scalar_one()
        if result == 1:
            return {"status": "ok"}
        return {"status": "error", "message": f"Unexpected SELECT 1 result: {result!r}"}
    except SQLAlchemyError as exc:
        logger.warning("Database health check failed: %s", exc)
        return {"status": "error", "message": str(exc)}
    finally:
        session.close()


def check_postgis_available() -> dict[str, Any]:
    """Probe ``PostGIS_Version()`` and return a structured status dict"""
    try:
        session = SessionLocal()
    except Exception as exc:  # pragma: no cover; defensive
        logger.exception("Failed to open database session for PostGIS probe")
        return {"status": "error", "message": str(exc)}
    try:
        version = session.execute(text("SELECT PostGIS_Version()")).scalar_one()
        return {"status": "ok", "version": str(version)}
    except SQLAlchemyError as exc:
        logger.warning("PostGIS health check failed: %s", exc)
        return {"status": "error", "message": str(exc)}
    finally:
        session.close()


def get_database_health() -> dict[str, Any]:
    """Combined database + PostGIS health payload"""
    return {
        "database": check_database_connection(),
        "postgis": check_postgis_available(),
    }


__all__ = [
    "check_database_connection",
    "check_postgis_available",
    "get_database_health",
]
