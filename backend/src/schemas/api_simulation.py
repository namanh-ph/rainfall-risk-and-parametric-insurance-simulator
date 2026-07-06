"""Request/response schemas for the simulation API endpoints"""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from src.domain.constants import (
    DEFAULT_PAYOUT_COVERAGE_MULTIPLIER,
    DEFAULT_PAYOUT_SIMULATION_ID,
    DEFAULT_PAYOUT_SIMULATION_NAME,
)

SensitivityMode = Literal["thresholds", "coverage_multipliers", "combined"]


class PayoutSimulationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    as_of_date: date = date(2025, 12, 31)
    simulation_id: str = Field(default=DEFAULT_PAYOUT_SIMULATION_ID, min_length=1, max_length=64)
    simulation_name: str = Field(
        default=DEFAULT_PAYOUT_SIMULATION_NAME, min_length=1, max_length=128
    )
    coverage_multiplier: float = Field(
        default=DEFAULT_PAYOUT_COVERAGE_MULTIPLIER, gt=0
    )
    asset_ids: list[str] | None = None
    replace_existing: bool = True
    include_risk_band: bool = True

    @field_validator("asset_ids")
    @classmethod
    def _no_empty_ids(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return value
        if not value:
            raise ValueError("asset_ids must be null or a non-empty list")
        if any(not isinstance(v, str) or not v.strip() for v in value):
            raise ValueError("every asset_id must be a non-empty string")
        return value


class PayoutSimulationResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    simulation_id: str
    simulation_name: str
    as_of_date: date
    coverage_multiplier: float
    assets_considered: int = Field(..., ge=0)
    feature_records_available: int = Field(..., ge=0)
    payout_records_generated: int = Field(..., ge=0)
    payout_records_inserted: int = Field(..., ge=0)
    triggered_assets: int = Field(..., ge=0)
    not_triggered_assets: int = Field(..., ge=0)
    total_coverage_limit: float = Field(..., ge=0)
    total_estimated_payout: float = Field(..., ge=0)
    average_payout_rate: float | None = None
    replace_existing: bool


class ThresholdSensitivityRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    as_of_date: date = date(2025, 12, 31)
    asset_ids: list[str] | None = None
    mode: SensitivityMode = "thresholds"
    replace_existing: bool = True
    include_risk_band: bool = True

    @field_validator("asset_ids")
    @classmethod
    def _no_empty_ids(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return value
        if not value:
            raise ValueError("asset_ids must be null or a non-empty list")
        if any(not isinstance(v, str) or not v.strip() for v in value):
            raise ValueError("every asset_id must be a non-empty string")
        return value


class ThresholdSensitivityScenarioResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    simulation_id: str
    simulation_name: str
    coverage_multiplier: float = Field(..., gt=0)
    payout_records_generated: int = Field(..., ge=0)
    payout_records_inserted: int = Field(..., ge=0)
    asset_count: int = Field(..., ge=0)
    triggered_assets: int = Field(..., ge=0)
    not_triggered_assets: int = Field(..., ge=0)
    trigger_rate: float = Field(..., ge=0, le=1)
    total_coverage_limit: float = Field(..., ge=0)
    total_estimated_payout: float = Field(..., ge=0)
    average_payout_rate: float = Field(..., ge=0, le=1)


class ThresholdSensitivityResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    as_of_date: date
    mode: SensitivityMode
    scenario_count: int = Field(..., ge=0)
    scenarios: list[ThresholdSensitivityScenarioResponse] = Field(default_factory=list)
    replace_existing: bool


__all__ = [
    "PayoutSimulationRequest",
    "PayoutSimulationResponse",
    "SensitivityMode",
    "ThresholdSensitivityRequest",
    "ThresholdSensitivityResponse",
    "ThresholdSensitivityScenarioResponse",
]
