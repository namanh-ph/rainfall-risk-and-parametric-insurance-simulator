"""Pydantic schemas for LightGBM training, evaluation, and MLflow tracking"""

from __future__ import annotations

from datetime import date
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class TrainingMetrics(BaseModel):
    """Classification + ranking metrics produced by one training run"""

    model_config = ConfigDict(extra="forbid")

    roc_auc: float | None = None
    pr_auc: float | None = None
    accuracy: float | None = None
    precision: float | None = None
    recall: float | None = None
    f1: float | None = None
    precision_at_top_10_pct: float | None = None
    recall_at_top_10_pct: float | None = None
    lift_at_top_10_pct: float | None = None
    positive_rate: float = Field(..., ge=0, le=1)
    train_row_count: int = Field(..., ge=0)
    test_row_count: int = Field(..., ge=0)
    feature_count: int = Field(..., gt=0)


class FeatureImportanceRecord(BaseModel):
    """One row of LightGBM feature importance"""

    model_config = ConfigDict(extra="forbid")

    feature: str = Field(..., min_length=1, max_length=128)
    importance_gain: float = Field(..., ge=0)
    importance_split: int = Field(..., ge=0)


class LightGbmTrainingRunSummary(BaseModel):
    """Top-level summary returned by ``run_lightgbm_training``"""

    model_config = ConfigDict(extra="forbid")

    model_name: str = Field(..., min_length=1, max_length=128)
    model_version: str = Field(..., min_length=1, max_length=64)
    as_of_date: date
    feature_version: str = Field(..., min_length=1, max_length=32)
    target_name: str = Field(..., min_length=1)
    train_row_count: int = Field(..., ge=0)
    test_row_count: int = Field(..., ge=0)
    feature_count: int = Field(..., gt=0)
    positive_count: int = Field(..., ge=0)
    negative_count: int = Field(..., ge=0)
    positive_rate: float = Field(..., ge=0, le=1)
    metrics: dict[str, Any]
    top_features: list[dict[str, Any]]
    artifact_path: str = Field(..., min_length=1)
    mlflow_logged: bool
    mlflow_run_id: str | None = None
    warnings: list[str]


__all__ = [
    "FeatureImportanceRecord",
    "LightGbmTrainingRunSummary",
    "TrainingMetrics",
]
