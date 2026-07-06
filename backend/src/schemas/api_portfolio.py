"""Pydantic response schemas for portfolio analytics endpoints"""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from src.schemas.api_common import PaginationMeta

RiskBand = Literal["Low", "Medium", "High", "Severe"]


class RiskBandDistributionItem(BaseModel):
    model_config = ConfigDict(extra="ignore")

    risk_band: RiskBand
    asset_count: int = Field(..., ge=0)
    average_risk_score: float | None = None
    total_coverage_limit: float = Field(..., ge=0)
    total_estimated_payout: float = Field(..., ge=0)


class IndustryRiskSummaryItem(BaseModel):
    model_config = ConfigDict(extra="ignore")

    industry: str
    asset_count: int = Field(..., ge=0)
    average_risk_score: float | None = None
    high_or_severe_assets: int = Field(..., ge=0)
    triggered_assets: int = Field(..., ge=0)
    total_coverage_limit: float = Field(..., ge=0)
    total_estimated_payout: float = Field(..., ge=0)


class LgaRiskSummaryItem(BaseModel):
    model_config = ConfigDict(extra="ignore")

    lga_code: str
    lga_name: str | None = None
    asset_count: int = Field(..., ge=0)
    average_risk_score: float | None = None
    high_or_severe_assets: int = Field(..., ge=0)
    triggered_assets: int = Field(..., ge=0)
    total_coverage_limit: float = Field(..., ge=0)
    total_estimated_payout: float = Field(..., ge=0)


class PortfolioSummaryResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    as_of_date: date
    simulation_id: str
    model_name: str
    model_version: str

    total_assets: int = Field(..., ge=0)
    total_asset_value: float = Field(..., ge=0)
    total_coverage_limit: float = Field(..., ge=0)
    average_risk_score: float | None = None
    high_or_severe_assets: int = Field(..., ge=0)
    triggered_assets: int = Field(..., ge=0)
    total_estimated_payout: float = Field(..., ge=0)
    average_ml_risk_probability: float | None = None

    risk_band_distribution: list[RiskBandDistributionItem] = Field(default_factory=list)
    industry_summary: list[IndustryRiskSummaryItem] = Field(default_factory=list)
    lga_summary: list[LgaRiskSummaryItem] = Field(default_factory=list)


class PortfolioRiskRankingItem(BaseModel):
    model_config = ConfigDict(extra="ignore")

    rank: int = Field(..., ge=1)
    asset_id: str
    business_type: str
    industry: str
    postcode: str
    lga_code: str | None = None
    lga_name: str | None = None
    asset_value: float
    coverage_limit: float
    risk_score: float | None = None
    risk_band: RiskBand | None = None
    rainfall_3d_mm: float | None = None
    rainfall_percentile: float | None = None
    extreme_rainfall_flag: bool | None = None
    trigger_status: str | None = None
    estimated_payout: float | None = None
    ml_risk_probability: float | None = None
    ml_risk_rank: int | None = None
    top_risk_driver: str | None = None


class PortfolioRiskRankingResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[PortfolioRiskRankingItem] = Field(default_factory=list)
    pagination: PaginationMeta
    sort_by: str
    sort_order: str
    as_of_date: date
    simulation_id: str
    model_name: str
    model_version: str


__all__ = [
    "IndustryRiskSummaryItem",
    "LgaRiskSummaryItem",
    "PortfolioRiskRankingItem",
    "PortfolioRiskRankingResponse",
    "PortfolioSummaryResponse",
    "RiskBand",
    "RiskBandDistributionItem",
]
