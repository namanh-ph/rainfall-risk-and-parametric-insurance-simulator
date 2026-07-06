"""Batch prediction pipeline.

Loads a trained LightGBM artefact from disk, aligns
``model_training_data.engineered_features_json`` rows to the trained
feature schema, computes ``ml_risk_probability`` per asset, ranks the
portfolio deterministically, infers a lightweight ``top_risk_driver``
(no SHAP), and persists rows to ``model_predictions``.

This module is strictly read-only against every upstream table; only
``model_predictions`` is written
"""

from __future__ import annotations

import csv
import json
import logging
import math
import pickle
from collections import Counter
from collections.abc import Iterable, Sequence
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np
from sqlalchemy import delete, select, tuple_
from sqlalchemy.orm import Session

from src.db.models import ModelPrediction, ModelTrainingData
from src.ml.dataset import DEFAULT_FEATURE_VERSION
from src.ml.training import _EXCLUDED_RAW_KEYS, _LEAKY_FEATURE_KEYS, TARGET_NAME
from src.schemas.ml_prediction import (
    BatchPredictionRunSummary,
    ModelPredictionRecord,
)

logger = logging.getLogger(__name__)

DEFAULT_AS_OF_DATE = date(2025, 12, 31)
DEFAULT_MODEL_NAME = "rainfall_risk_lgbm"
DEFAULT_MODEL_VERSION = "v1"
ARTIFACTS_ROOT = Path("backend/artifacts/models")


def _default_artifact_dir(
    model_name: str, model_version: str, as_of_date: date
) -> Path:
    return ARTIFACTS_ROOT / f"{model_name}_{model_version}_{as_of_date.isoformat()}"


def load_feature_importance(
    feature_importance_path: str | Path,
) -> list[dict[str, Any]]:
    """Read ``feature_importance.csv`` sorted by ``importance_gain`` descending"""
    path = Path(feature_importance_path)
    if not path.is_file():
        return []
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        for record in reader:
            feature = record.get("feature")
            if not feature:
                continue
            try:
                gain = float(record.get("importance_gain", 0) or 0)
            except (TypeError, ValueError):
                gain = 0.0
            try:
                split = int(float(record.get("importance_split", 0) or 0))
            except (TypeError, ValueError):
                split = 0
            rows.append(
                {
                    "feature": feature,
                    "importance_gain": gain,
                    "importance_split": split,
                }
            )
    rows.sort(key=lambda r: r["importance_gain"], reverse=True)
    return rows


def load_model_artifacts(
    artifact_dir: str | Path,
    expected_model_name: str | None = None,
    expected_model_version: str | None = None,
    expected_feature_version: str | None = None,
    expected_as_of_date: date | None = None,
) -> dict[str, Any]:
    """Load ``model.pkl`` + ``metadata.json`` + ``feature_names.json``.

    Raises ``FileNotFoundError`` when required files are missing and
    ``ValueError`` when metadata conflicts with the expected values.
    ``feature_importance.csv`` is optional
    """
    base = Path(artifact_dir)
    if not base.is_dir():
        raise FileNotFoundError(f"Artefact directory not found: {base}")

    model_path = base / "model.pkl"
    metadata_path = base / "metadata.json"
    feature_names_path = base / "feature_names.json"
    importance_path = base / "feature_importance.csv"

    for required in (model_path, metadata_path, feature_names_path):
        if not required.is_file():
            raise FileNotFoundError(
                f"Required model artefact missing: {required}"
            )

    with model_path.open("rb") as fh:
        model = pickle.load(fh)
    with metadata_path.open(encoding="utf-8") as fh:
        metadata = json.load(fh)
    with feature_names_path.open(encoding="utf-8") as fh:
        feature_names = json.load(fh)
    if not isinstance(feature_names, list) or not all(
        isinstance(n, str) for n in feature_names
    ):
        raise ValueError(
            f"feature_names.json at {feature_names_path} must be a list of strings"
        )

    _validate_metadata(
        metadata,
        expected_model_name=expected_model_name,
        expected_model_version=expected_model_version,
        expected_feature_version=expected_feature_version,
        expected_as_of_date=expected_as_of_date,
    )

    feature_importance = load_feature_importance(importance_path)

    return {
        "model": model,
        "metadata": metadata,
        "feature_names": feature_names,
        "feature_importance": feature_importance,
        "artifact_dir": str(base),
    }


def _validate_metadata(
    metadata: dict[str, Any],
    *,
    expected_model_name: str | None,
    expected_model_version: str | None,
    expected_feature_version: str | None,
    expected_as_of_date: date | None,
) -> None:
    def _conflict(field: str, expected: Any, actual: Any) -> None:
        raise ValueError(
            f"metadata.json {field} {actual!r} does not match expected {expected!r}"
        )

    if expected_model_name is not None and metadata.get("model_name") != expected_model_name:
        _conflict("model_name", expected_model_name, metadata.get("model_name"))
    if (
        expected_model_version is not None
        and metadata.get("model_version") != expected_model_version
    ):
        _conflict("model_version", expected_model_version, metadata.get("model_version"))
    if (
        expected_feature_version is not None
        and metadata.get("feature_version") != expected_feature_version
    ):
        _conflict(
            "feature_version", expected_feature_version, metadata.get("feature_version")
        )
    if expected_as_of_date is not None:
        actual = metadata.get("as_of_date")
        if isinstance(actual, str):
            try:
                actual_date = date.fromisoformat(actual)
            except ValueError:
                actual_date = None
        elif isinstance(actual, date):
            actual_date = actual
        else:
            actual_date = None
        if actual_date != expected_as_of_date:
            _conflict("as_of_date", expected_as_of_date.isoformat(), actual)


def load_prediction_rows(
    db: Session,
    as_of_date: date | None = None,
    feature_version: str = DEFAULT_FEATURE_VERSION,
    asset_ids: Sequence[str] | None = None,
) -> list[dict[str, Any]]:
    """Load rows from ``model_training_data`` for inference"""
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


def flatten_prediction_rows(
    rows: Sequence[dict[str, Any]],
) -> tuple[list[dict[str, float]], list[str], list[str]]:
    """Project ``model_training_data`` rows into numeric feature rows.

    Returns ``(feature_rows, asset_ids, feature_names)``. The target
    field is excluded explicitly so prediction never reads it
    """
    if not rows:
        raise ValueError("flatten_prediction_rows received an empty row list")

    excluded = set(_EXCLUDED_RAW_KEYS) | set(_LEAKY_FEATURE_KEYS) | {TARGET_NAME}
    candidate_keys: set[str] = set()
    blocked_keys: set[str] = set()
    for row in rows:
        payload = row.get("engineered_features_json") or {}
        for key, value in payload.items():
            if key in excluded:
                blocked_keys.add(key)
                continue
            if isinstance(value, str):
                blocked_keys.add(key)
                continue
            if value is None or isinstance(value, (bool, int, float)):
                candidate_keys.add(key)
                continue
            blocked_keys.add(key)

    feature_names = sorted(candidate_keys - blocked_keys)
    if not feature_names:
        raise ValueError(
            "No usable numeric features in prediction rows after filtering"
        )

    feature_rows: list[dict[str, float]] = []
    asset_ids: list[str] = []
    for row in rows:
        payload = row.get("engineered_features_json") or {}
        feature_dict = {name: _coerce_feature_value(payload.get(name)) for name in feature_names}
        feature_rows.append(feature_dict)
        asset_ids.append(str(row["asset_id"]))
    return feature_rows, asset_ids, feature_names


def align_features_to_model(
    feature_rows: Sequence[dict[str, float]],
    model_feature_names: Sequence[str],
) -> tuple[np.ndarray, list[str]]:
    """Build the inference matrix in trained ``model_feature_names`` order"""
    warnings: list[str] = []
    if not feature_rows:
        raise ValueError("align_features_to_model received an empty feature_rows list")
    inference_keys = set(feature_rows[0].keys())
    missing = [name for name in model_feature_names if name not in inference_keys]
    extras = sorted(inference_keys - set(model_feature_names))
    if missing:
        warnings.append(
            f"{len(missing)} model features missing from inference rows; filled with NaN"
        )
    if extras:
        warnings.append(
            f"{len(extras)} extra inference features ignored ({extras[:5]}{'…' if len(extras) > 5 else ''})"
        )

    matrix = np.array(
        [
            [row.get(name, float("nan")) for name in model_feature_names]
            for row in feature_rows
        ],
        dtype=float,
    )
    return matrix, warnings


def generate_prediction_probabilities(
    model: Any, feature_matrix: np.ndarray
) -> list[float]:
    """Call ``model.predict_proba`` and return the positive-class column"""
    proba = model.predict_proba(feature_matrix)
    proba = np.asarray(proba, dtype=float)
    positive = (
        proba[:, 1] if proba.ndim == 2 and proba.shape[1] >= 2 else proba.reshape(-1)
    )
    out: list[float] = []
    for p in positive:
        if not math.isfinite(p):
            out.append(0.0)
        else:
            out.append(float(max(0.0, min(1.0, p))))
    return out


def calculate_prediction_ranks(
    asset_ids: Sequence[str], probabilities: Sequence[float]
) -> dict[str, int]:
    """Return ``{asset_id: rank}`` with rank 1 for the highest probability.

    Ties on probability are broken deterministically by ``asset_id`` ascending
    """
    if len(asset_ids) != len(probabilities):
        raise ValueError("asset_ids and probabilities must have the same length")
    pairs = sorted(
        zip(asset_ids, probabilities, strict=True), key=lambda x: (-x[1], x[0])
    )
    return {aid: rank for rank, (aid, _) in enumerate(pairs, start=1)}


def infer_top_risk_driver(
    feature_row: dict[str, float],
    model_feature_names: Sequence[str],
    feature_importance: Sequence[dict[str, Any]] | None = None,
) -> str | None:
    """Deterministic feature-importance-driven top driver (no SHAP).

    Algorithm:
      1. If ``feature_importance`` is available, iterate its features
         (already sorted by ``importance_gain`` descending) and return
         the first one that exists in ``model_feature_names`` and has a
         finite numeric value on this asset.
      2. Otherwise, fall back to the feature with the largest absolute
         finite value among the model's feature columns. Returns
         ``None`` when no finite values are available
    """
    model_names = set(model_feature_names)

    if feature_importance:
        for entry in feature_importance:
            name = entry.get("feature")
            if not name or name not in model_names:
                continue
            value = feature_row.get(name)
            if isinstance(value, (int, float)) and math.isfinite(float(value)):
                return str(name)
        return None

    best_name: str | None = None
    best_abs: float = -1.0
    for name in model_feature_names:
        value = feature_row.get(name)
        if isinstance(value, (int, float)) and math.isfinite(float(value)):
            absolute = abs(float(value))
            if absolute > best_abs:
                best_abs = absolute
                best_name = str(name)
    return best_name


def build_model_prediction_records(
    rows: Sequence[dict[str, Any]],
    probabilities: Sequence[float],
    ranks: dict[str, int],
    model_name: str,
    model_version: str,
    as_of_date: date,
    model_feature_names: Sequence[str],
    feature_importance: Sequence[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Build the per-asset prediction records"""
    if len(rows) != len(probabilities):
        raise ValueError("rows and probabilities must have the same length")
    out: list[dict[str, Any]] = []
    for row, probability in zip(rows, probabilities, strict=True):
        asset_id = str(row["asset_id"])
        payload = row.get("engineered_features_json") or {}
        # The flattened feature row maps directly from the same payload,
        # so re-coerce here to keep the top-driver path self-contained
        feature_row = {
            name: _coerce_feature_value(payload.get(name)) for name in model_feature_names
        }
        top_driver = infer_top_risk_driver(
            feature_row, model_feature_names, feature_importance
        )
        out.append(
            {
                "asset_id": asset_id,
                "as_of_date": as_of_date,
                "model_name": model_name,
                "model_version": model_version,
                "ml_risk_probability": round(float(probability), 5),
                "ml_risk_rank": int(ranks[asset_id]),
                "top_risk_driver": top_driver,
            }
        )
    return out


def validate_model_prediction_records(
    records: Iterable[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Validate each record + uniqueness on the (asset_id, as_of_date, model_name, model_version) tuple"""
    seen: set[tuple[str, date, str, str]] = set()
    out: list[dict[str, Any]] = []
    for record in records:
        validated = ModelPredictionRecord.model_validate(record)
        key = (
            validated.asset_id,
            validated.as_of_date,
            validated.model_name,
            validated.model_version,
        )
        if key in seen:
            raise ValueError(
                f"Duplicate (asset_id, as_of_date, model_name, model_version) in batch: {key}"
            )
        seen.add(key)
        out.append(validated.model_dump())
    return out


def persist_model_predictions(
    records: Sequence[dict[str, Any]],
    db: Session,
    replace_existing: bool = True,
) -> int:
    """Insert prediction rows; replace or skip duplicates by the quadruplet"""
    if not records:
        return 0

    validated = validate_model_prediction_records(records)
    keys = [
        (r["asset_id"], r["as_of_date"], r["model_name"], r["model_version"])
        for r in validated
    ]

    try:
        if replace_existing:
            db.execute(
                delete(ModelPrediction).where(
                    tuple_(
                        ModelPrediction.asset_id,
                        ModelPrediction.as_of_date,
                        ModelPrediction.model_name,
                        ModelPrediction.model_version,
                    ).in_(keys)
                )
            )
            to_insert = validated
        else:
            existing_rows = db.execute(
                select(
                    ModelPrediction.asset_id,
                    ModelPrediction.as_of_date,
                    ModelPrediction.model_name,
                    ModelPrediction.model_version,
                ).where(
                    tuple_(
                        ModelPrediction.asset_id,
                        ModelPrediction.as_of_date,
                        ModelPrediction.model_name,
                        ModelPrediction.model_version,
                    ).in_(keys)
                )
            ).all()
            existing_keys = {
                (row[0], row[1], row[2], row[3]) for row in existing_rows
            }
            if existing_keys:
                logger.warning(
                    "Skipping %d existing model_predictions rows", len(existing_keys)
                )
            to_insert = [
                r
                for r in validated
                if (r["asset_id"], r["as_of_date"], r["model_name"], r["model_version"])
                not in existing_keys
            ]

        orm_rows = [
            ModelPrediction(
                asset_id=r["asset_id"],
                as_of_date=r["as_of_date"],
                model_name=r["model_name"],
                model_version=r["model_version"],
                ml_risk_probability=r["ml_risk_probability"],
                ml_risk_rank=r["ml_risk_rank"],
                top_risk_driver=r["top_risk_driver"],
            )
            for r in to_insert
        ]
        if orm_rows:
            db.add_all(orm_rows)
        db.commit()
        return len(orm_rows)
    except Exception:
        db.rollback()
        raise


def run_batch_prediction(
    db: Session,
    artifact_dir: str | Path | None = None,
    as_of_date: date | None = None,
    feature_version: str = DEFAULT_FEATURE_VERSION,
    model_name: str = DEFAULT_MODEL_NAME,
    model_version: str = DEFAULT_MODEL_VERSION,
    asset_ids: Sequence[str] | None = None,
    replace_existing: bool = True,
) -> dict[str, Any]:
    """Run the batch-prediction pipeline and return a structured summary"""
    effective_as_of = as_of_date or DEFAULT_AS_OF_DATE
    effective_dir = (
        Path(artifact_dir)
        if artifact_dir is not None
        else _default_artifact_dir(model_name, model_version, effective_as_of)
    )

    artefacts = load_model_artifacts(
        effective_dir,
        expected_model_name=model_name,
        expected_model_version=model_version,
        expected_feature_version=feature_version,
        expected_as_of_date=effective_as_of,
    )
    model = artefacts["model"]
    model_feature_names = artefacts["feature_names"]
    feature_importance = artefacts["feature_importance"]

    rows = load_prediction_rows(
        db,
        as_of_date=effective_as_of,
        feature_version=feature_version,
        asset_ids=asset_ids,
    )
    if not rows:
        raise ValueError(
            "No model_training_data rows available for prediction; "
            f"as_of_date={effective_as_of}, feature_version={feature_version!r}"
        )

    feature_rows, prediction_asset_ids, _flattened_names = flatten_prediction_rows(rows)
    matrix, alignment_warnings = align_features_to_model(feature_rows, model_feature_names)

    probabilities = generate_prediction_probabilities(model, matrix)
    ranks = calculate_prediction_ranks(prediction_asset_ids, probabilities)
    records = build_model_prediction_records(
        rows=rows,
        probabilities=probabilities,
        ranks=ranks,
        model_name=model_name,
        model_version=model_version,
        as_of_date=effective_as_of,
        model_feature_names=model_feature_names,
        feature_importance=feature_importance,
    )
    inserted = persist_model_predictions(records, db, replace_existing=replace_existing)

    min_p: float | None = None
    median_p: float | None = None
    max_p: float | None = None
    top_ranked_asset: str | None = None
    if probabilities:
        sorted_p = sorted(probabilities)
        median_p = sorted_p[len(sorted_p) // 2]
        min_p, max_p = sorted_p[0], sorted_p[-1]
        top_ranked_asset = min(
            zip(prediction_asset_ids, probabilities, strict=True),
            key=lambda x: (-x[1], x[0]),
        )[0]

    driver_counts = Counter(
        r["top_risk_driver"] for r in records if r["top_risk_driver"] is not None
    )

    summary: dict[str, Any] = {
        "model_name": model_name,
        "model_version": model_version,
        "as_of_date": effective_as_of,
        "feature_version": feature_version,
        "artifact_dir": str(effective_dir),
        "records_loaded": len(rows),
        "prediction_records_generated": len(records),
        "prediction_records_inserted": inserted,
        "min_probability": round(min_p, 5) if min_p is not None else None,
        "median_probability": round(median_p, 5) if median_p is not None else None,
        "max_probability": round(max_p, 5) if max_p is not None else None,
        "top_ranked_asset_id": top_ranked_asset,
        "top_risk_driver_counts": dict(driver_counts),
        "warnings": list(alignment_warnings),
        "replace_existing": replace_existing,
    }
    BatchPredictionRunSummary.model_validate(summary)
    return summary


__all__ = [
    "DEFAULT_AS_OF_DATE",
    "DEFAULT_MODEL_NAME",
    "DEFAULT_MODEL_VERSION",
    "align_features_to_model",
    "build_model_prediction_records",
    "calculate_prediction_ranks",
    "flatten_prediction_rows",
    "generate_prediction_probabilities",
    "infer_top_risk_driver",
    "load_feature_importance",
    "load_model_artifacts",
    "load_prediction_rows",
    "persist_model_predictions",
    "run_batch_prediction",
    "validate_model_prediction_records",
]
