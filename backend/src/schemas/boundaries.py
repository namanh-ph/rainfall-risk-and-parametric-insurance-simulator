"""Pydantic schemas for LGA boundary ingestion.

Metadata-only — geometry validation lives in
``backend/src/ingestion/boundaries.py`` because Shapely geometries
don't round-trip cleanly through Pydantic v2.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class LgaBoundaryCreate(BaseModel):
    """DB-insertable LGA boundary metadata (no ``geom``)."""

    model_config = ConfigDict(extra="ignore")

    lga_code: str = Field(..., min_length=1, max_length=16)
    lga_name: str = Field(..., min_length=1, max_length=128)
    state: str = Field(default="VIC", min_length=1, max_length=8)
    data_source: str = Field(default="local_boundary_file", min_length=1, max_length=64)


class LgaBoundaryCsvRecord(LgaBoundaryCreate):
    """CSV/GeoJSON-source LGA record. Extras (``geometry``, ``properties``,
    raw column names) flow through unchecked."""

    model_config = ConfigDict(extra="allow")


__all__ = ["LgaBoundaryCreate", "LgaBoundaryCsvRecord"]
