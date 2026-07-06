"""LightGBM training pipeline + artefact persistence.

Reads from ``model_training_data`` (no upstream tables touched), flattens
``engineered_features_json`` into a numeric modelling frame, builds a
deterministic asset-hash train/test split, trains a LightGBM binary
classifier with class-imbalance handling, evaluates it, and saves local
artefacts. MLflow logging is best-effort and never blocks artefact
creation
"""

from __future__ import annotations

import csv
import json
import logging
import math
import pickle
from collections.abc import Iterable, Sequence
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import numpy as np
from sqlalchemy import bindparam, select, text
from sqlalchemy.orm import Session

from src.db.models import ModelTrainingData
from src.ml.evaluation import (
    build_feature_importance_frame,
    calculate_binary_classification_metrics,
    calculate_ranking_metrics,
)
from src.ml.splits import assign_train_test_split
from src.ml.tracking import (
    DEFAULT_EXPERIMENT_NAME,
    log_training_run_to_mlflow,
)
from src.schemas.ml_training import LightGbmTrainingRunSummary

logger = logging.getLogger(__name__)

DEFAULT_AS_OF_DATE = date(2025, 12, 31)
DEFAULT_FEATURE_VERSION = "rainfall_risk_features_v1"
DEFAULT_MODEL_NAME = "rainfall_risk_lgbm"
DEFAULT_MODEL_VERSION = "v1"
TARGET_NAME = "target_extreme_rainfall_event"

# Raw string fields that must NOT be modelled directly. Their encoded
# numeric counterparts (`industry_code`, ...) flow into the model instead
_EXCLUDED_RAW_KEYS: frozenset[str] = frozenset(
    {
        "industry",
        "business_type",
        "postcode",
        "lga_code",
        "lga_name",
        "station_id",
        "risk_band",
        "baseline_trigger_status",
    }
)

# Features that leak the target. The target is derived from
# extreme_rainfall_flag, rainfall_percentile >= 0.95, or
# rainfall_3d_mm >= 3 * rainfall_p95_station (see
# ``derive_target_extreme_rainfall_event``). Any feature that participates
# in those rules, or is computed downstream from them (risk score, payouts,
# their aggregates), must not enter the model
_LEAKY_FEATURE_KEYS: frozenset[str] = frozenset(
    {
        # direct rule inputs
        "extreme_rainfall_flag",
        "rainfall_percentile",
        "rainfall_3d_mm",
        "rainfall_p95_station",
        "rainfall_3d_to_p95_ratio",
        # ratios that reuse rule inputs in numerator or denominator
        "rainfall_3d_to_p99_ratio",
        "rainfall_30d_to_p95_ratio",
        # rule-based risk score chain (uses rainfall_extreme_score)
        "rainfall_extreme_score",
        "raw_score",
        "risk_score",
        "risk_band_code",
        # payouts triggered by the same rainfall thresholds as the target
        "baseline_payout_rate",
        "baseline_estimated_payout",
        "baseline_triggered_flag",
        "sensitive_threshold_triggered_flag",
        "very_sensitive_threshold_triggered_flag",
        "max_sensitivity_payout_rate",
        "max_sensitivity_estimated_payout",
    }
)


def load_training_rows(
    db: Session,
    as_of_date: date | None = None,
    feature_version: str = DEFAULT_FEATURE_VERSION,
    asset_ids: Sequence[str] | None = None,
) -> list[dict[str, Any]]:
    """Load ``model_training_data`` rows matching the filter"""
    effective_as_of = as_of_date or DEFAULT_AS_OF_DATE
    stmt = (
        select(
            ModelTrainingData.asset_id,
            ModelTrainingData.as_of_date,
            ModelTrainingData.feature_version,
            ModelTrainingData.target_extreme_rainfall_event,
            ModelTrainingData.engineered_features_json,
        )
        .where(ModelTrainingData.as_of_date == effective_as_of)
        .where(ModelTrainingData.feature_version == feature_version)
        .order_by(ModelTrainingData.asset_id)
    )
    if asset_ids is not None:
        stmt = stmt.where(ModelTrainingData.asset_id.in_(list(asset_ids)))

    rows = db.execute(stmt).all()
    out: list[dict[str, Any]] = []
    for row in rows:
        out.append(
            {
                "asset_id": str(row[0]),
                "as_of_date": row[1],
                "feature_version": str(row[2]),
                "target_extreme_rainfall_event": bool(row[3]),
                "engineered_features_json": row[4] or {},
            }
        )
    return out


def flatten_training_rows(
    rows: Sequence[dict[str, Any]],
) -> tuple[list[dict[str, float]], list[int], list[str]]:
    """Project rows into ``(feature_rows, targets, asset_ids)``.

    Numeric keys (int / float / bool / None) survive. Excluded raw string
    keys and any key that ever holds a string anywhere in the batch are
    dropped. Booleans coerce to 0.0 / 1.0; None becomes ``float('nan')``.
    Feature ordering is sorted lexicographically
    """
    if not rows:
        raise ValueError("flatten_training_rows received an empty row list")

    candidate_keys: set[str] = set()
    blocked_keys: set[str] = set()
    for row in rows:
        payload = row.get("engineered_features_json") or {}
        for key, value in payload.items():
            if key in _EXCLUDED_RAW_KEYS or key in _LEAKY_FEATURE_KEYS:
                blocked_keys.add(key)
                continue
            if isinstance(value, str):
                blocked_keys.add(key)
                continue
            if value is None or isinstance(value, (bool, int, float)):
                candidate_keys.add(key)
                continue
            # Unsupported types (list, dict, ...); exclude conservatively
            blocked_keys.add(key)

    feature_names = sorted(candidate_keys - blocked_keys)
    if not feature_names:
        raise ValueError(
            "No usable numeric features in training rows after filtering"
        )

    feature_rows: list[dict[str, float]] = []
    targets: list[int] = []
    asset_ids: list[str] = []
    for row in rows:
        payload = row.get("engineered_features_json") or {}
        feature_dict: dict[str, float] = {}
        for name in feature_names:
            value = payload.get(name)
            feature_dict[name] = _coerce_feature_value(value)
        feature_rows.append(feature_dict)
        targets.append(int(bool(row["target_extreme_rainfall_event"])))
        asset_ids.append(str(row["asset_id"]))
    return feature_rows, targets, asset_ids


def _coerce_feature_value(value: Any) -> float:
    if value is None:
        return float("nan")
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    try:
        result = float(value)
    except (TypeError, ValueError):
        return float("nan")
    return result


def build_train_test_matrices(
    feature_rows: Sequence[dict[str, float]],
    targets: Sequence[int],
    asset_ids: Sequence[str],
    feature_names: Sequence[str],
    test_size: float = 0.2,
    split_seed: int = 42,
) -> dict[str, Any]:
    """Build numpy train/test matrices using the deterministic split"""
    if len(feature_rows) != len(targets) or len(targets) != len(asset_ids):
        raise ValueError(
            "feature_rows, targets, and asset_ids must all be the same length"
        )
    if not feature_names:
        raise ValueError("feature_names must be non-empty")

    train_idx: list[int] = []
    test_idx: list[int] = []
    for i, aid in enumerate(asset_ids):
        if assign_train_test_split(aid, test_size=test_size, seed=split_seed) == "test":
            test_idx.append(i)
        else:
            train_idx.append(i)

    def _matrix(indices: Sequence[int]) -> np.ndarray:
        if not indices:
            return np.zeros((0, len(feature_names)), dtype=float)
        data = [
            [feature_rows[i].get(name, float("nan")) for name in feature_names]
            for i in indices
        ]
        return np.asarray(data, dtype=float)

    return {
        "X_train": _matrix(train_idx),
        "X_test": _matrix(test_idx),
        "y_train": [int(targets[i]) for i in train_idx],
        "y_test": [int(targets[i]) for i in test_idx],
        "train_asset_ids": [str(asset_ids[i]) for i in train_idx],
        "test_asset_ids": [str(asset_ids[i]) for i in test_idx],
        "feature_names": list(feature_names),
    }


def calculate_scale_pos_weight(targets: Iterable[int]) -> float:
    """Return ``negative_count / positive_count``; raise if either is zero"""
    target_list = list(targets)
    positive = sum(1 for t in target_list if t)
    negative = len(target_list) - positive
    if positive == 0:
        raise ValueError(
            "Cannot calculate scale_pos_weight: no positive targets in batch"
        )
    if negative == 0:
        raise ValueError(
            "Cannot calculate scale_pos_weight: no negative targets in batch"
        )
    return float(negative) / float(positive)


def train_lightgbm_model(
    train_matrix: np.ndarray,
    train_targets: Sequence[int],
    params: dict[str, Any],
) -> Any:
    """Fit a LightGBM binary classifier on the supplied train data"""
    import lightgbm as lgb  # local import keeps the module import cheap

    model = lgb.LGBMClassifier(**params)
    model.fit(np.asarray(train_matrix, dtype=float), np.asarray(list(train_targets), dtype=int))
    return model


def save_training_artifacts(
    model: Any,
    metadata: dict[str, Any],
    metrics: dict[str, Any],
    feature_names: Sequence[str],
    feature_importance: Sequence[dict[str, Any]],
    output_dir: str | Path,
) -> dict[str, Path]:
    """Persist model + metadata + metrics + feature names + importance CSV"""
    path = Path(output_dir)
    path.mkdir(parents=True, exist_ok=True)

    model_path = path / "model.pkl"
    metadata_path = path / "metadata.json"
    feature_names_path = path / "feature_names.json"
    metrics_path = path / "metrics.json"
    feature_importance_path = path / "feature_importance.csv"

    with model_path.open("wb") as fh:
        pickle.dump(model, fh)

    with metadata_path.open("w", encoding="utf-8") as fh:
        json.dump(metadata, fh, indent=2, default=str)

    with feature_names_path.open("w", encoding="utf-8") as fh:
        json.dump(list(feature_names), fh, indent=2)

    with metrics_path.open("w", encoding="utf-8") as fh:
        json.dump(metrics, fh, indent=2, default=str)

    with feature_importance_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(
            fh, fieldnames=["feature", "importance_gain", "importance_split"]
        )
        writer.writeheader()
        for entry in feature_importance:
            writer.writerow(
                {
                    "feature": entry["feature"],
                    "importance_gain": entry["importance_gain"],
                    "importance_split": entry["importance_split"],
                }
            )

    return {
        "model": model_path,
        "metadata": metadata_path,
        "feature_names": feature_names_path,
        "metrics": metrics_path,
        "feature_importance": feature_importance_path,
    }


def _default_output_dir(
    model_name: str, model_version: str, as_of_date: date
) -> Path:
    return (
        Path("backend") / "artifacts" / "models"
        / f"{model_name}_{model_version}_{as_of_date.isoformat()}"
    )


def run_lightgbm_training(
    db: Session,
    as_of_date: date | None = None,
    feature_version: str = DEFAULT_FEATURE_VERSION,
    model_name: str = DEFAULT_MODEL_NAME,
    model_version: str = DEFAULT_MODEL_VERSION,
    asset_ids: Sequence[str] | None = None,
    test_size: float = 0.2,
    split_seed: int = 42,
    random_state: int = 42,
    output_dir: str | Path | None = None,
    experiment_name: str = DEFAULT_EXPERIMENT_NAME,
    log_to_mlflow: bool = True,
) -> dict[str, Any]:
    """Train LightGBM, evaluate, save artefacts, log to MLflow, return summary"""
    effective_as_of = as_of_date or DEFAULT_AS_OF_DATE

    rows = load_training_rows(
        db, as_of_date=effective_as_of, feature_version=feature_version, asset_ids=asset_ids
    )
    if not rows:
        raise ValueError(
            f"No model_training_data rows for as_of_date={effective_as_of}, "
            f"feature_version={feature_version!r}; run build_training_data first."
        )

    feature_rows, targets, asset_id_list = flatten_training_rows(rows)
    feature_names = list(feature_rows[0].keys()) if feature_rows else []
    if not feature_names:
        raise ValueError("No usable numeric features in training rows")

    positive_count = sum(1 for t in targets if t)
    negative_count = len(targets) - positive_count
    if positive_count == 0 or negative_count == 0:
        raise ValueError(
            f"Training requires both classes (got {positive_count} positives, "
            f"{negative_count} negatives); training aborted."
        )

    scale_pos_weight = calculate_scale_pos_weight(targets)

    matrices = build_train_test_matrices(
        feature_rows,
        targets,
        asset_id_list,
        feature_names,
        test_size=test_size,
        split_seed=split_seed,
    )

    params = {
        "objective": "binary",
        "n_estimators": 200,
        "learning_rate": 0.05,
        "num_leaves": 31,
        "max_depth": -1,
        "min_child_samples": 20,
        "subsample": 0.9,
        "colsample_bytree": 0.9,
        "random_state": random_state,
        "scale_pos_weight": scale_pos_weight,
        "verbose": -1,
    }

    model = train_lightgbm_model(matrices["X_train"], matrices["y_train"], params)

    # Evaluation
    if matrices["X_test"].shape[0] > 0:
        probabilities = model.predict_proba(matrices["X_test"])[:, 1].tolist()
    else:
        probabilities = []
    classification_metrics = calculate_binary_classification_metrics(
        matrices["y_test"], probabilities
    )
    ranking_metrics = calculate_ranking_metrics(matrices["y_test"], probabilities)

    positive_rate = (
        positive_count / (positive_count + negative_count)
        if (positive_count + negative_count) > 0
        else 0.0
    )

    metrics = {
        **classification_metrics,
        **ranking_metrics,
        "positive_rate": round(positive_rate, 6),
        "train_row_count": int(matrices["X_train"].shape[0]),
        "test_row_count": int(matrices["X_test"].shape[0]),
        "feature_count": len(feature_names),
    }

    feature_importance = build_feature_importance_frame(model, feature_names)

    output_path = (
        Path(output_dir)
        if output_dir is not None
        else _default_output_dir(model_name, model_version, effective_as_of)
    )

    metadata: dict[str, Any] = {
        "model_name": model_name,
        "model_version": model_version,
        "as_of_date": effective_as_of.isoformat(),
        "feature_version": feature_version,
        "target_name": TARGET_NAME,
        "random_state": random_state,
        "test_size": test_size,
        "split_seed": split_seed,
        "train_row_count": metrics["train_row_count"],
        "test_row_count": metrics["test_row_count"],
        "feature_count": metrics["feature_count"],
        "positive_count": positive_count,
        "negative_count": negative_count,
        "mlflow_run_id": None,
        "artifact_path": str(output_path),
        "created_at": datetime.now(UTC).isoformat(),
    }

    artefact_paths = save_training_artifacts(
        model=model,
        metadata=metadata,
        metrics=metrics,
        feature_names=feature_names,
        feature_importance=feature_importance,
        output_dir=output_path,
    )

    warnings: list[str] = []
    mlflow_logged = False
    mlflow_run_id: str | None = None
    if log_to_mlflow:
        mlflow_result = log_training_run_to_mlflow(
            params=params,
            metrics=dict(metrics),
            artifacts=artefact_paths,
            model=model,
            experiment_name=experiment_name,
        )
        mlflow_logged = bool(mlflow_result.get("mlflow_logged"))
        mlflow_run_id = mlflow_result.get("mlflow_run_id")
        if not mlflow_logged and mlflow_result.get("warning"):
            warnings.append(str(mlflow_result["warning"]))

    # Rewrite metadata.json with the run id if MLflow succeeded
    if mlflow_run_id is not None:
        metadata["mlflow_run_id"] = mlflow_run_id
        with (output_path / "metadata.json").open("w", encoding="utf-8") as fh:
            json.dump(metadata, fh, indent=2, default=str)

    top_features = sorted(
        feature_importance,
        key=lambda r: float(r["importance_gain"]),
        reverse=True,
    )[:10]

    summary = {
        "model_name": model_name,
        "model_version": model_version,
        "as_of_date": effective_as_of,
        "feature_version": feature_version,
        "target_name": TARGET_NAME,
        "train_row_count": metrics["train_row_count"],
        "test_row_count": metrics["test_row_count"],
        "feature_count": metrics["feature_count"],
        "positive_count": positive_count,
        "negative_count": negative_count,
        "positive_rate": round(positive_rate, 6),
        "metrics": metrics,
        "top_features": top_features,
        "artifact_path": str(output_path),
        "mlflow_logged": mlflow_logged,
        "mlflow_run_id": mlflow_run_id,
        "warnings": warnings,
    }
    LightGbmTrainingRunSummary.model_validate(summary)
    return summary


# Silence a no-op import the linter may flag in tight paths
_ = (bindparam, text, math)

__all__ = [
    "DEFAULT_AS_OF_DATE",
    "DEFAULT_FEATURE_VERSION",
    "DEFAULT_MODEL_NAME",
    "DEFAULT_MODEL_VERSION",
    "TARGET_NAME",
    "build_train_test_matrices",
    "calculate_scale_pos_weight",
    "flatten_training_rows",
    "load_training_rows",
    "run_lightgbm_training",
    "save_training_artifacts",
    "train_lightgbm_model",
]
