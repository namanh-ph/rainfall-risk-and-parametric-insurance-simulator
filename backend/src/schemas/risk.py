"""Pydantic schemas for rule-based rainfall risk scoring"""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.domain.constants import (
    RISK_BAND_HIGH,
    RISK_BAND_LOW,
    RISK_BAND_MEDIUM,
    RISK_BAND_SEVERE,
)

RiskBand = Literal["Low", "Medium", "High", "Severe"]


class AssetRiskScoreRecord(BaseModel):
    """One rule-based risk score row for an (asset, as_of_date) pair"""

    model_config = ConfigDict(extra="ignore")

    asset_id: str = Field(..., min_length=1, max_length=64)
    as_of_date: date

    rainfall_extreme_score: float = Field(..., ge=0, le=100)
    exposure_weight: float = Field(..., ge=0.8, le=1.3)
    vulnerability_weight: float = Field(..., ge=0.8, le=1.4)
    station_confidence_weight: float = Field(..., ge=0.50, le=1.00)

    raw_score: float = Field(..., ge=0)
    risk_score: float = Field(..., ge=0, le=100)
    risk_band: RiskBand


class AssetRiskScoringRunSummary(BaseModel):
    """Structured summary returned by ``run_asset_risk_scoring``"""

    model_config = ConfigDict(extra="forbid")

    assets_considered: int = Field(..., ge=0)
    feature_records_available: int = Field(..., ge=0)
    station_mappings_available: int = Field(..., ge=0)
    as_of_date: date
    risk_score_records_generated: int = Field(..., ge=0)
    risk_score_records_inserted: int = Field(..., ge=0)
    low_risk_assets: int = Field(..., ge=0)
    medium_risk_assets: int = Field(..., ge=0)
    high_risk_assets: int = Field(..., ge=0)
    severe_risk_assets: int = Field(..., ge=0)
    average_risk_score: float | None = Field(default=None, ge=0, le=100)
    replace_existing: bool

    @model_validator(mode="after")
    def _bands_sum_to_generated(self) -> AssetRiskScoringRunSummary:
        bands_sum = (
            self.low_risk_assets
            + self.medium_risk_assets
            + self.high_risk_assets
            + self.severe_risk_assets
        )
        if bands_sum != self.risk_score_records_generated:
            raise ValueError(
                f"risk band counts ({bands_sum}) must sum to "
                f"risk_score_records_generated ({self.risk_score_records_generated})"
            )
        return self


__all__ = [
    "RISK_BAND_HIGH",
    "RISK_BAND_LOW",
    "RISK_BAND_MEDIUM",
    "RISK_BAND_SEVERE",
    "AssetRiskScoreRecord",
    "AssetRiskScoringRunSummary",
    "RiskBand",
]
