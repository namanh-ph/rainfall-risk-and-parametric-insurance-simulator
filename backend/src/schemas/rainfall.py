"""Pydantic schemas for rainfall station and observation ingestion"""

from __future__ import annotations

from datetime import date
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from src.schemas.assets import VIC_LAT_MAX, VIC_LAT_MIN, VIC_LON_MAX, VIC_LON_MIN


def _empty_to_none(value: Any) -> Any:
    if isinstance(value, str) and value.strip() == "":
        return None
    return value


class RainfallStationCreate(BaseModel):
    """DB-insertable station fields (no geom)"""

    model_config = ConfigDict(extra="ignore")

    station_id: str = Field(..., min_length=1, max_length=32)
    station_name: str = Field(..., min_length=1, max_length=255)
    latitude: float = Field(..., ge=VIC_LAT_MIN, le=VIC_LAT_MAX)
    longitude: float = Field(..., ge=VIC_LON_MIN, le=VIC_LON_MAX)
    elevation_m: float | None = Field(default=None)
    data_source: str = Field(..., min_length=1, max_length=64)

    @field_validator("elevation_m", mode="before")
    @classmethod
    def _coerce_blank_elevation(cls, value: Any) -> Any:
        return _empty_to_none(value)


class RainfallStationCsvRecord(RainfallStationCreate):
    """CSV-source station record (allows extra columns for future fields)"""

    model_config = ConfigDict(extra="allow")


class RainfallObservationCreate(BaseModel):
    """DB-insertable observation fields (excludes ``observation_id``)"""

    model_config = ConfigDict(extra="ignore")

    station_id: str = Field(..., min_length=1, max_length=32)
    observation_date: date
    rainfall_mm: float = Field(..., ge=0)
    quality_flag: str | None = Field(default=None, max_length=8)

    @field_validator("quality_flag", mode="before")
    @classmethod
    def _coerce_blank_quality_flag(cls, value: Any) -> Any:
        return _empty_to_none(value)


class RainfallObservationCsvRecord(RainfallObservationCreate):
    """CSV-source observation record (allows extra columns)"""

    model_config = ConfigDict(extra="allow")


__all__ = [
    "RainfallObservationCreate",
    "RainfallObservationCsvRecord",
    "RainfallStationCreate",
    "RainfallStationCsvRecord",
]
