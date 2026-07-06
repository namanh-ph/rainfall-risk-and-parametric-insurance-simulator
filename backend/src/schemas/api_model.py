"""Pydantic response schemas for model metadata and prediction endpoints"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from src.schemas.api_common import PaginationMeta

RiskBand = Literal["Low", "Medium", "High", "Severe"]


class ModelMetadataResponse(BaseModel):
    """Local artefact metadata + persisted prediction availability"""

    model_config = ConfigDict(extra="ignore")

    model_name: str
    model_version: str
    as_of_date: date
    feature_version: str | None = None
    target_name: str | None = None
    artifact_path: str | None = None
    metrics: dict[str, Any] | None = None
    feature_count: int | None = None
    train_row_count: int | None = None
    test_row_count: int | None = None
    positive_count: int | None = None
    negative_count: int | None = None
    positive_rate: float | None = None
    mlflow_logged: bool | None = None
    mlflow_run_id: str | None = None
    prediction_count: int = Field(..., ge=0)
    created_at: datetime | None = None


class ModelPredictionItem(BaseModel):
    model_config = ConfigDict(extra="ignore")

    asset_id: str
    business_type: str | None = None
    industry: str | None = None
    postcode: str | None = None
    lga_code: str | None = None
    lga_name: str | None = None
    risk_score: float | None = None
    risk_band: RiskBand | None = None
    ml_risk_probability: float = Field(..., ge=0, le=1)
    ml_risk_rank: int | None = Field(default=None, ge=1)
    top_risk_driver: str | None = None
    as_of_date: date
    model_name: str
    model_version: str


class ModelPredictionListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[ModelPredictionItem] = Field(default_factory=list)
    pagination: PaginationMeta
    model_name: str
    model_version: str
    as_of_date: date
    sort_by: str
    sort_order: str


class ModelPredictionDetailResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    asset_id: str
    business_type: str | None = None
    industry: str | None = None
    postcode: str | None = None
    lga_code: str | None = None
    lga_name: str | None = None
    risk_score: float | None = None
    risk_band: RiskBand | None = None
    rainfall_3d_mm: float | None = None
    rainfall_percentile: float | None = None
    extreme_rainfall_flag: bool | None = None
    ml_risk_probability: float = Field(..., ge=0, le=1)
    ml_risk_rank: int | None = Field(default=None, ge=1)
    top_risk_driver: str | None = None
    as_of_date: date
    model_name: str
    model_version: str


__all__ = [
    "ModelMetadataResponse",
    "ModelPredictionDetailResponse",
    "ModelPredictionItem",
    "ModelPredictionListResponse",
    "RiskBand",
]
