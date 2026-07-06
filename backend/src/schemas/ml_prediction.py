"""Pydantic schemas for batch prediction generation"""

from __future__ import annotations

import math
from datetime import date

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ModelPredictionRecord(BaseModel):
    """One row of the ``model_predictions`` table"""

    model_config = ConfigDict(extra="ignore")

    asset_id: str = Field(..., min_length=1, max_length=64)
    as_of_date: date
    model_name: str = Field(..., min_length=1, max_length=128)
    model_version: str = Field(..., min_length=1, max_length=64)
    ml_risk_probability: float = Field(..., ge=0, le=1)
    ml_risk_rank: int = Field(..., ge=1)
    top_risk_driver: str | None = Field(default=None, max_length=128)

    @field_validator("top_risk_driver")
    @classmethod
    def _empty_string_not_allowed(cls, v: str | None) -> str | None:
        if v is None:
            return None
        stripped = v.strip()
        return stripped or None


class BatchPredictionRunSummary(BaseModel):
    """Structured summary returned by ``run_batch_prediction``"""

    model_config = ConfigDict(extra="forbid")

    model_name: str = Field(..., min_length=1, max_length=128)
    model_version: str = Field(..., min_length=1, max_length=64)
    as_of_date: date
    feature_version: str = Field(..., min_length=1, max_length=32)
    artifact_dir: str = Field(..., min_length=1)
    records_loaded: int = Field(..., ge=0)
    prediction_records_generated: int = Field(..., ge=0)
    prediction_records_inserted: int = Field(..., ge=0)
    min_probability: float | None = Field(default=None, ge=0, le=1)
    median_probability: float | None = Field(default=None, ge=0, le=1)
    max_probability: float | None = Field(default=None, ge=0, le=1)
    top_ranked_asset_id: str | None
    top_risk_driver_counts: dict[str, int]
    warnings: list[str]
    replace_existing: bool

    @field_validator("min_probability", "median_probability", "max_probability")
    @classmethod
    def _finite_or_none(cls, v: float | None) -> float | None:
        if v is None:
            return None
        if not math.isfinite(v):
            raise ValueError("probability must be a finite number when provided")
        return v


__all__ = ["BatchPredictionRunSummary", "ModelPredictionRecord"]
