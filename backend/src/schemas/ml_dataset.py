"""Pydantic schemas for ML training dataset construction"""

from __future__ import annotations

from datetime import date
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ModelTrainingRecord(BaseModel):
    """One row of the ``model_training_data`` table"""

    model_config = ConfigDict(extra="ignore")

    asset_id: str = Field(..., min_length=1, max_length=64)
    as_of_date: date
    feature_version: str = Field(..., min_length=1, max_length=32)
    target_extreme_rainfall_event: bool
    engineered_features_json: dict[str, Any] = Field(..., min_length=1)


class ModelTrainingDataBuildSummary(BaseModel):
    """Structured summary returned by ``run_model_training_data_build``"""

    model_config = ConfigDict(extra="forbid")

    as_of_date: date
    feature_version: str = Field(..., min_length=1, max_length=32)
    baseline_simulation_id: str = Field(..., min_length=1, max_length=64)
    assets_considered: int = Field(..., ge=0)
    records_generated: int = Field(..., ge=0)
    records_inserted: int = Field(..., ge=0)
    positive_targets: int = Field(..., ge=0)
    negative_targets: int = Field(..., ge=0)
    positive_target_rate: float = Field(..., ge=0, le=1)
    feature_payload_key_count: int = Field(..., ge=0)
    categorical_encoder_counts: dict[str, int]
    replace_existing: bool

    @model_validator(mode="after")
    def _target_counts_match(self) -> ModelTrainingDataBuildSummary:
        if self.positive_targets + self.negative_targets != self.records_generated:
            raise ValueError(
                f"positive_targets ({self.positive_targets}) + "
                f"negative_targets ({self.negative_targets}) must equal "
                f"records_generated ({self.records_generated})"
            )
        return self


class TrainTestSplitSummary(BaseModel):
    """Summary of the deterministic train/test split"""

    model_config = ConfigDict(extra="forbid")

    train_count: int = Field(..., ge=0)
    test_count: int = Field(..., ge=0)
    total_count: int = Field(..., ge=0)
    test_rate: float = Field(..., ge=0, le=1)
    seed: int
    test_size: float = Field(..., gt=0, lt=1)

    @model_validator(mode="after")
    def _counts_match(self) -> TrainTestSplitSummary:
        if self.train_count + self.test_count != self.total_count:
            raise ValueError(
                f"train_count ({self.train_count}) + test_count ({self.test_count}) "
                f"must equal total_count ({self.total_count})"
            )
        return self


__all__ = [
    "ModelTrainingDataBuildSummary",
    "ModelTrainingRecord",
    "TrainTestSplitSummary",
]
