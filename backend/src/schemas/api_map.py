"""Pydantic-compatible GeoJSON wrappers for ``/map/*`` endpoints."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class GeoJsonFeature(BaseModel):
    """One Feature inside a FeatureCollection.

    ``geometry`` is intentionally typed as ``dict | None`` rather than a
    strict GeoJSON union — PostGIS already produces well-formed
    geometry dicts via ``ST_AsGeoJSON``.
    """

    model_config = ConfigDict(extra="forbid")

    type: Literal["Feature"] = "Feature"
    geometry: dict[str, Any] | None
    properties: dict[str, Any] = Field(default_factory=dict)


class GeoJsonFeatureCollection(BaseModel):
    """RFC 7946 FeatureCollection envelope."""

    model_config = ConfigDict(extra="forbid")

    type: Literal["FeatureCollection"] = "FeatureCollection"
    features: list[GeoJsonFeature] = Field(default_factory=list)


__all__ = ["GeoJsonFeature", "GeoJsonFeatureCollection"]
