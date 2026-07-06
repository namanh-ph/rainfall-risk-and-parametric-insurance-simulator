"""Pydantic schemas for simulation tracking and threshold sensitivity"""

from __future__ import annotations

from datetime import date
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class SimulationConfig(BaseModel):
    """Reusable simulation configuration for one ``simulation_runs`` row"""

    model_config = ConfigDict(extra="ignore")

    simulation_id: str = Field(..., min_length=1, max_length=64)
    simulation_name: str = Field(..., min_length=1, max_length=128)
    as_of_date: date
    threshold_config: list[dict[str, Any]] = Field(..., min_length=1)
    coverage_multiplier: float = Field(..., gt=0)


class PortfolioPayoutSummary(BaseModel):
    """Portfolio-level aggregate of one scenario's per-asset payout records"""

    model_config = ConfigDict(extra="forbid")

    asset_count: int = Field(..., ge=0)
    triggered_assets: int = Field(..., ge=0)
    not_triggered_assets: int = Field(..., ge=0)
    trigger_rate: float = Field(..., ge=0, le=1)
    total_coverage_limit: float = Field(..., ge=0)
    total_estimated_payout: float = Field(..., ge=0)
    average_payout_rate: float = Field(..., ge=0, le=1)
    average_estimated_payout: float = Field(..., ge=0)
    max_estimated_payout: float = Field(..., ge=0)
    payout_rate_distribution: dict[str, int]

    @model_validator(mode="after")
    def _internal_consistency(self) -> PortfolioPayoutSummary:
        if self.triggered_assets + self.not_triggered_assets != self.asset_count:
            raise ValueError(
                f"triggered_assets ({self.triggered_assets}) + "
                f"not_triggered_assets ({self.not_triggered_assets}) must equal "
                f"asset_count ({self.asset_count})"
            )
        dist_total = sum(self.payout_rate_distribution.values())
        if dist_total != self.asset_count:
            raise ValueError(
                f"payout_rate_distribution counts ({dist_total}) must sum to "
                f"asset_count ({self.asset_count})"
            )
        for count in self.payout_rate_distribution.values():
            if count < 0:
                raise ValueError("payout_rate_distribution counts must be non-negative")
        return self


class SimulationScenarioResult(BaseModel):
    """Result envelope for one scenario inside a sensitivity sweep"""

    model_config = ConfigDict(extra="forbid")

    simulation_id: str = Field(..., min_length=1, max_length=64)
    simulation_name: str = Field(..., min_length=1, max_length=128)
    threshold_config: list[dict[str, Any]] = Field(..., min_length=1)
    coverage_multiplier: float = Field(..., gt=0)
    payout_records_generated: int = Field(..., ge=0)
    payout_records_inserted: int = Field(..., ge=0)
    summary: PortfolioPayoutSummary


class ThresholdSensitivityRunSummary(BaseModel):
    """Top-level summary returned by ``run_threshold_sensitivity``"""

    model_config = ConfigDict(extra="forbid")

    as_of_date: date
    scenario_count: int = Field(..., ge=0)
    scenarios: list[SimulationScenarioResult]
    replace_existing: bool

    @model_validator(mode="after")
    def _scenario_count_matches(self) -> ThresholdSensitivityRunSummary:
        if self.scenario_count != len(self.scenarios):
            raise ValueError(
                f"scenario_count ({self.scenario_count}) must equal "
                f"len(scenarios) ({len(self.scenarios)})"
            )
        return self


class CoverageMultiplierSensitivityRunSummary(BaseModel):
    """Top-level summary returned by ``run_coverage_multiplier_sensitivity``"""

    model_config = ConfigDict(extra="forbid")

    as_of_date: date
    scenario_count: int = Field(..., ge=0)
    scenarios: list[SimulationScenarioResult]
    replace_existing: bool

    @model_validator(mode="after")
    def _scenario_count_matches(self) -> CoverageMultiplierSensitivityRunSummary:
        if self.scenario_count != len(self.scenarios):
            raise ValueError(
                f"scenario_count ({self.scenario_count}) must equal "
                f"len(scenarios) ({len(self.scenarios)})"
            )
        return self


class CombinedSensitivityRunSummary(BaseModel):
    """Top-level summary returned by ``run_combined_sensitivity``"""

    model_config = ConfigDict(extra="forbid")

    as_of_date: date
    threshold_sensitivity: ThresholdSensitivityRunSummary
    coverage_multiplier_sensitivity: CoverageMultiplierSensitivityRunSummary
    replace_existing: bool


__all__ = [
    "CombinedSensitivityRunSummary",
    "CoverageMultiplierSensitivityRunSummary",
    "PortfolioPayoutSummary",
    "SimulationConfig",
    "SimulationScenarioResult",
    "ThresholdSensitivityRunSummary",
]
