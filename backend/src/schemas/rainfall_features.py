"""Pydantic schemas for rainfall feature engineering"""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, ConfigDict, Field, model_validator


class RainfallFeatureRecord(BaseModel):
    """One engineered rainfall feature row for an (asset, as_of_date) pair"""

    model_config = ConfigDict(extra="ignore")

    asset_id: str = Field(..., min_length=1, max_length=64)
    station_id: str = Field(..., min_length=1, max_length=32)
    as_of_date: date

    rainfall_1d_mm: float = Field(..., ge=0)
    rainfall_3d_mm: float = Field(..., ge=0)
    rainfall_7d_mm: float = Field(..., ge=0)
    rainfall_30d_mm: float = Field(..., ge=0)

    rainfall_p95_station: float | None = Field(default=None, ge=0)
    rainfall_p99_station: float | None = Field(default=None, ge=0)
    rainfall_percentile: float | None = Field(default=None, ge=0, le=1)
    max_365d_rainfall_mm: float | None = Field(default=None, ge=0)
    days_above_p95_365d: int | None = Field(default=None, ge=0)

    extreme_rainfall_flag: bool


class RainfallFeatureRunSummary(BaseModel):
    """Structured summary returned by ``run_rainfall_feature_generation``"""

    model_config = ConfigDict(extra="forbid")

    assets_considered: int = Field(..., ge=0)
    mapped_assets: int = Field(..., ge=0)
    stations_used: int = Field(..., ge=0)
    as_of_date: date
    lookback_start_date: date
    lookback_end_date: date
    feature_records_generated: int = Field(..., ge=0)
    feature_records_inserted: int = Field(..., ge=0)
    assets_without_station_mapping: int = Field(..., ge=0)
    assets_without_observations: int = Field(..., ge=0)
    extreme_rainfall_assets: int = Field(..., ge=0)
    replace_existing: bool

    @model_validator(mode="after")
    def _validate_window(self) -> RainfallFeatureRunSummary:
        if self.lookback_start_date > self.lookback_end_date:
            raise ValueError(
                "lookback_start_date must be <= lookback_end_date "
                f"({self.lookback_start_date} > {self.lookback_end_date})"
            )
        if self.as_of_date != self.lookback_end_date:
            raise ValueError(
                "as_of_date must equal lookback_end_date "
                f"({self.as_of_date} != {self.lookback_end_date})"
            )
        return self


__all__ = ["RainfallFeatureRecord", "RainfallFeatureRunSummary"]
