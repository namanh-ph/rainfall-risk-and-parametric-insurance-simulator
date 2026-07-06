"""Shared FastAPI dependencies for the API surface"""

from __future__ import annotations

from datetime import date

from fastapi import HTTPException, Query, status

from src.db.session import get_db

DEFAULT_AS_OF_DATE = date(2025, 12, 31)


def pagination_params(
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> dict[str, int]:
    """Validate and bundle pagination query parameters"""
    return {"limit": limit, "offset": offset}


def map_limit_param(
    limit: int = Query(5000, ge=1, le=10000),
) -> int:
    """Validate the ``limit`` parameter for map-asset endpoints"""
    return limit


def parse_as_of_date(
    as_of_date: date | None = Query(None, description="As-of date (YYYY-MM-DD)"),
) -> date:
    """Return ``as_of_date`` or the default of 2025-12-31"""
    return as_of_date or DEFAULT_AS_OF_DATE


def validate_asset_id(asset_id: str) -> str:
    """Lightweight validation of asset_id path parameters"""
    if not asset_id or len(asset_id) > 64:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="asset_id must be a non-empty string <= 64 characters",
        )
    return asset_id


def validate_risk_band(value: str | None) -> str | None:
    if value is None:
        return None
    if value not in ("Low", "Medium", "High", "Severe"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "risk_band must be one of Low, Medium, High, Severe "
                f"(got {value!r})"
            ),
        )
    return value


__all__ = [
    "DEFAULT_AS_OF_DATE",
    "get_db",
    "map_limit_param",
    "pagination_params",
    "parse_as_of_date",
    "validate_asset_id",
    "validate_risk_band",
]
