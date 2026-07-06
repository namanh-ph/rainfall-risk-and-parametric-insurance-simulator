"""Pydantic schemas for asset-to-station nearest-neighbour matching"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from src.domain.constants import STATION_CONFIDENCE_FLOOR


class StationMatchRecord(BaseModel):
    """One nearest-station match; what gets persisted into asset_station_mapping"""

    model_config = ConfigDict(extra="ignore")

    asset_id: str = Field(..., min_length=1, max_length=64)
    station_id: str = Field(..., min_length=1, max_length=32)
    station_distance_km: float = Field(..., ge=0)
    station_confidence_weight: float = Field(
        ..., ge=STATION_CONFIDENCE_FLOOR, le=1.0
    )
    matched_at: datetime


class StationMatchingRunSummary(BaseModel):
    """Structured summary returned by ``run_asset_station_matching``"""

    model_config = ConfigDict(extra="forbid")

    assets_considered: int = Field(..., ge=0)
    stations_available: int = Field(..., ge=0)
    matches_generated: int = Field(..., ge=0)
    mappings_inserted: int = Field(..., ge=0)
    unmatched_assets: int = Field(..., ge=0)
    max_distance_km: float | None = Field(default=None, gt=0)
    replace_existing: bool


__all__ = ["StationMatchRecord", "StationMatchingRunSummary"]
