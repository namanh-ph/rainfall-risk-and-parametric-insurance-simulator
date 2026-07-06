"""Pydantic response schemas for asset endpoints"""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from src.schemas.api_common import PaginationMeta

RiskBand = Literal["Low", "Medium", "High", "Severe"]


class AssetListItem(BaseModel):
    """One row in ``GET /assets`` results"""

    model_config = ConfigDict(extra="ignore")

    asset_id: str
    business_type: str
    industry: str
    postcode: str
    latitude: float
    longitude: float
    asset_value: float
    annual_revenue: float | None = None
    coverage_limit: float
    lga_code: str | None = None
    lga_name: str | None = None
    risk_score: float | None = None
    risk_band: RiskBand | None = None
    rainfall_3d_mm: float | None = None
    station_id: str | None = None
    station_distance_km: float | None = None
    ml_risk_probability: float | None = None
    ml_risk_rank: int | None = None


class AssetDetail(BaseModel):
    """Detailed payload returned by ``GET /assets/{asset_id}``"""

    model_config = ConfigDict(extra="ignore")

    asset_id: str
    business_type: str
    industry: str
    postcode: str
    latitude: float
    longitude: float
    asset_value: float
    annual_revenue: float | None = None
    coverage_limit: float
    lga_code: str | None = None
    lga_name: str | None = None
    risk_score: float | None = None
    risk_band: RiskBand | None = None
    rainfall_1d_mm: float | None = None
    rainfall_3d_mm: float | None = None
    rainfall_7d_mm: float | None = None
    rainfall_30d_mm: float | None = None
    rainfall_percentile: float | None = None
    extreme_rainfall_flag: bool | None = None
    station_id: str | None = None
    station_name: str | None = None
    station_distance_km: float | None = None
    station_confidence_weight: float | None = None
    ml_risk_probability: float | None = None
    ml_risk_rank: int | None = None
    top_risk_driver: str | None = None


class AssetRiskResponse(BaseModel):
    """Persisted rule-based risk score for one asset and as_of_date"""

    model_config = ConfigDict(extra="ignore")

    asset_id: str
    as_of_date: date
    rainfall_extreme_score: float
    exposure_weight: float
    vulnerability_weight: float
    station_confidence_weight: float
    raw_score: float
    risk_score: float
    risk_band: RiskBand


class AssetRainfallResponse(BaseModel):
    """Persisted rainfall features for one asset and as_of_date"""

    model_config = ConfigDict(extra="ignore")

    asset_id: str
    station_id: str
    as_of_date: date
    rainfall_1d_mm: float
    rainfall_3d_mm: float
    rainfall_7d_mm: float
    rainfall_30d_mm: float
    rainfall_p95_station: float | None = None
    rainfall_p99_station: float | None = None
    rainfall_percentile: float | None = None
    max_365d_rainfall_mm: float | None = None
    days_above_p95_365d: int | None = None
    extreme_rainfall_flag: bool


class AssetStationResponse(BaseModel):
    """Nearest-station mapping for one asset"""

    model_config = ConfigDict(extra="ignore")

    asset_id: str
    station_id: str
    station_name: str
    latitude: float
    longitude: float
    station_distance_km: float
    station_confidence_weight: float
    matched_at: datetime
    data_source: str | None = None


class AssetListResponse(BaseModel):
    """Wrapper for ``GET /assets``: ``{items, pagination}``"""

    model_config = ConfigDict(extra="forbid")

    items: list[AssetListItem] = Field(default_factory=list)
    pagination: PaginationMeta


__all__ = [
    "AssetDetail",
    "AssetListItem",
    "AssetListResponse",
    "AssetRainfallResponse",
    "AssetRiskResponse",
    "AssetStationResponse",
    "RiskBand",
]
