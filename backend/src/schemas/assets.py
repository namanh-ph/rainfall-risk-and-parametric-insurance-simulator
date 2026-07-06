"""Pydantic schemas for asset CSV ingestion and DB persistence.

`StaticAssetCsvRecord` validates the wider 44-column static CSV (extras
allowed) so downstream analytics can keep modelling-only fields. Only the
9-field subset survives projection into ``AssetDbCreate``
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

# Victoria-plausible bounding box used by ingestion validators
VIC_LAT_MIN = -39.3
VIC_LAT_MAX = -33.9
VIC_LON_MIN = 140.7
VIC_LON_MAX = 150.2


def _empty_to_none(value: Any) -> Any:
    if isinstance(value, str) and value.strip() == "":
        return None
    return value


class AssetDbCreate(BaseModel):
    """DB-insertable fields for the ``Asset`` ORM model (no geom)"""

    model_config = ConfigDict(extra="ignore")

    asset_id: str = Field(..., min_length=1, max_length=64)
    business_type: str = Field(..., min_length=1, max_length=64)
    industry: str = Field(..., min_length=1, max_length=128)
    postcode: str = Field(..., min_length=1, max_length=128)
    lga_code: str | None = Field(default=None, max_length=16)

    latitude: float = Field(..., ge=VIC_LAT_MIN, le=VIC_LAT_MAX)
    longitude: float = Field(..., ge=VIC_LON_MIN, le=VIC_LON_MAX)

    asset_value: float = Field(..., gt=0)
    annual_revenue: float | None = Field(default=None, ge=0)
    coverage_limit: float = Field(..., gt=0)

    @field_validator("annual_revenue", mode="before")
    @classmethod
    def _coerce_blank_revenue_to_none(cls, value: Any) -> Any:
        return _empty_to_none(value)

    @model_validator(mode="after")
    def _coverage_limit_must_not_exceed_asset_value(self) -> AssetDbCreate:
        if self.coverage_limit > self.asset_value:
            raise ValueError(
                f"coverage_limit ({self.coverage_limit}) must not exceed "
                f"asset_value ({self.asset_value})"
            )
        return self


class StaticAssetCsvRecord(BaseModel):
    """Validate the fields of one row from the static asset CSV.

    The wider modelling/policy columns (``stock_value``, ``policy_excess``,
    ``coverage_band``, ...) flow through unchecked via ``extra='allow'`` so
    consumers can still read them off the model if needed
    """

    model_config = ConfigDict(extra="allow")

    asset_id: str = Field(..., min_length=1, max_length=64)
    business_type: str = Field(..., min_length=1, max_length=64)
    industry: str = Field(..., min_length=1, max_length=128)
    postcode: str = Field(..., min_length=1, max_length=128)

    latitude: float = Field(..., ge=VIC_LAT_MIN, le=VIC_LAT_MAX)
    longitude: float = Field(..., ge=VIC_LON_MIN, le=VIC_LON_MAX)

    asset_value: float = Field(..., gt=0)
    annual_revenue: float | None = Field(default=None, ge=0)
    coverage_limit: float = Field(..., gt=0)

    @field_validator("annual_revenue", mode="before")
    @classmethod
    def _coerce_blank_revenue_to_none(cls, value: Any) -> Any:
        return _empty_to_none(value)

    @model_validator(mode="after")
    def _coverage_limit_must_not_exceed_asset_value(self) -> StaticAssetCsvRecord:
        if self.coverage_limit > self.asset_value:
            raise ValueError(
                f"coverage_limit ({self.coverage_limit}) must not exceed "
                f"asset_value ({self.asset_value})"
            )
        return self


__all__ = [
    "VIC_LAT_MAX",
    "VIC_LAT_MIN",
    "VIC_LON_MAX",
    "VIC_LON_MIN",
    "AssetDbCreate",
    "StaticAssetCsvRecord",
]
