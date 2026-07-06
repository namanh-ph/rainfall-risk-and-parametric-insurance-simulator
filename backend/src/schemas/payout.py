"""Pydantic schemas for parametric rainfall payouts"""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from src.domain.constants import RISK_BANDS

TriggerStatus = Literal["triggered", "not_triggered"]


class PayoutThreshold(BaseModel):
    """One tier of the payout-threshold table"""

    model_config = ConfigDict(extra="ignore")

    min_rainfall_3d_mm: float = Field(..., ge=0)
    max_rainfall_3d_mm: float | None = None
    payout_rate: float = Field(..., ge=0, le=1)

    @model_validator(mode="after")
    def _max_must_exceed_min(self) -> PayoutThreshold:
        if (
            self.max_rainfall_3d_mm is not None
            and self.max_rainfall_3d_mm <= self.min_rainfall_3d_mm
        ):
            raise ValueError(
                f"max_rainfall_3d_mm ({self.max_rainfall_3d_mm}) must be greater than "
                f"min_rainfall_3d_mm ({self.min_rainfall_3d_mm})"
            )
        return self


class PayoutResultRecord(BaseModel):
    """One row in the ``payout_results`` table"""

    model_config = ConfigDict(extra="ignore")

    simulation_id: str = Field(..., min_length=1, max_length=64)
    asset_id: str = Field(..., min_length=1, max_length=64)
    rainfall_3d_mm: float = Field(..., ge=0)
    trigger_status: TriggerStatus
    payout_rate: float = Field(..., ge=0, le=1)
    coverage_limit: float = Field(..., ge=0)
    estimated_payout: float = Field(..., ge=0)
    risk_band: str | None = Field(default=None, max_length=16)

    @field_validator("risk_band")
    @classmethod
    def _validate_risk_band(cls, value: str | None) -> str | None:
        if value is None:
            return value
        if value not in RISK_BANDS:
            raise ValueError(
                f"risk_band must be null or one of {RISK_BANDS} (got {value!r})"
            )
        return value

    @model_validator(mode="after")
    def _trigger_status_consistent_with_rate(self) -> PayoutResultRecord:
        if self.payout_rate == 0 and self.trigger_status != "not_triggered":
            raise ValueError(
                "trigger_status must be 'not_triggered' when payout_rate == 0"
            )
        if self.payout_rate > 0 and self.trigger_status != "triggered":
            raise ValueError(
                "trigger_status must be 'triggered' when payout_rate > 0"
            )
        return self


class PayoutSimulationRunSummary(BaseModel):
    """Structured summary returned by ``run_payout_simulation``"""

    model_config = ConfigDict(extra="forbid")

    simulation_id: str = Field(..., min_length=1, max_length=64)
    simulation_name: str = Field(..., min_length=1, max_length=128)
    as_of_date: date
    coverage_multiplier: float = Field(..., gt=0)
    assets_considered: int = Field(..., ge=0)
    feature_records_available: int = Field(..., ge=0)
    payout_records_generated: int = Field(..., ge=0)
    payout_records_inserted: int = Field(..., ge=0)
    triggered_assets: int = Field(..., ge=0)
    not_triggered_assets: int = Field(..., ge=0)
    total_coverage_limit: float = Field(..., ge=0)
    total_estimated_payout: float = Field(..., ge=0)
    average_payout_rate: float | None = Field(default=None, ge=0, le=1)
    replace_existing: bool

    @model_validator(mode="after")
    def _trigger_counts_match_generated(self) -> PayoutSimulationRunSummary:
        if (
            self.triggered_assets + self.not_triggered_assets
            != self.payout_records_generated
        ):
            raise ValueError(
                f"triggered_assets ({self.triggered_assets}) + "
                f"not_triggered_assets ({self.not_triggered_assets}) must equal "
                f"payout_records_generated ({self.payout_records_generated})"
            )
        return self


__all__ = [
    "PayoutResultRecord",
    "PayoutSimulationRunSummary",
    "PayoutThreshold",
    "TriggerStatus",
]
