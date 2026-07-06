"""Tests for the LightGBM training pipeline"""

from __future__ import annotations

import json
import pickle
import random
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from src.ml import training as training_module
from src.ml.training import (
    DEFAULT_FEATURE_VERSION,
    DEFAULT_MODEL_NAME,
    DEFAULT_MODEL_VERSION,
    build_train_test_matrices,
    calculate_scale_pos_weight,
    flatten_training_rows,
    load_training_rows,
    run_lightgbm_training,
    save_training_artifacts,
    train_lightgbm_model,
)


def _synthetic_payload(rainfall_3d: float, percentile: float, asset_value: float) -> dict[str, Any]:
    return {
        "asset_value": asset_value,
        "coverage_limit": asset_value * 0.1,
        "log_asset_value": float(np.log1p(asset_value)),
        "industry_code": 3,
        "business_type_code": 5,
        "postcode_code": 7,
        "lga_code_encoded": 2,
        "risk_band_code": 2,
        "station_distance_km": 5.5,
        "station_confidence_weight": 0.95,
        "has_lga_assignment": True,
        "latitude": -37.8,
        "longitude": 145.0,
        "rainfall_1d_mm": rainfall_3d / 3,
        "rainfall_3d_mm": rainfall_3d,
        "rainfall_7d_mm": rainfall_3d * 1.5,
        "rainfall_30d_mm": rainfall_3d * 4,
        "rainfall_p95_station": 7.5,
        "rainfall_p99_station": 14.0,
        "rainfall_percentile": percentile,
        "max_365d_rainfall_mm": 80.0,
        "days_above_p95_365d": 18,
        "extreme_rainfall_flag": rainfall_3d > 40,
        "rainfall_3d_to_p95_ratio": rainfall_3d / 7.5,
        "risk_score": 60.0,
        "raw_score": 70.0,
        "rainfall_extreme_score": 50.0,
        "exposure_weight": 1.1,
        "vulnerability_weight": 1.2,
        "baseline_payout_rate": 0.0,
        "baseline_estimated_payout": 0.0,
        "baseline_triggered_flag": False,
        "sensitive_threshold_triggered_flag": False,
        "very_sensitive_threshold_triggered_flag": False,
        # Raw string fields that must be excluded
        "industry": "retail",
        "business_type": "shop",
        "postcode": "Richmond",
        "lga_code": "LGA20660",
        "lga_name": "Melbourne",
        "station_id": "086282",
        "risk_band": "High",
        "baseline_trigger_status": "not_triggered",
    }


def _synthetic_rows(n: int = 200, seed: int = 1) -> list[dict[str, Any]]:
    rng = random.Random(seed)
    rows = []
    for i in range(n):
        # Two classes: positives have higher rainfall percentile + 3d total
        if i < n // 5:  # 20% positives
            rainfall_3d = rng.uniform(40, 80)
            percentile = rng.uniform(0.85, 1.0)
        else:
            rainfall_3d = rng.uniform(0, 10)
            percentile = rng.uniform(0.0, 0.5)
        payload = _synthetic_payload(
            rainfall_3d=rainfall_3d,
            percentile=percentile,
            asset_value=rng.uniform(500_000, 2_500_000),
        )
        rows.append(
            {
                "asset_id": f"VIC{i:04d}",
                "as_of_date": date(2025, 12, 31),
                "feature_version": DEFAULT_FEATURE_VERSION,
                "target_extreme_rainfall_event": i < n // 5,
                "engineered_features_json": payload,
            }
        )
    return rows


def test_load_training_rows_returns_rows_from_mocked_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected = _synthetic_rows(n=3)

    class _FakeRow:
        def __init__(self, r: dict[str, Any]) -> None:
            self._t = (
                r["asset_id"],
                r["as_of_date"],
                r["feature_version"],
                r["target_extreme_rainfall_event"],
                r["engineered_features_json"],
            )

        def __getitem__(self, i: int) -> Any:
            return self._t[i]

    class _FakeResult:
        def __init__(self, rows: list[Any]) -> None:
            self._rows = rows

        def all(self) -> list[Any]:
            return self._rows

    class FakeSession:
        def execute(self, stmt: Any) -> _FakeResult:
            return _FakeResult([_FakeRow(r) for r in expected])

    rows = load_training_rows(FakeSession())
    assert len(rows) == 3
    assert rows[0]["asset_id"] == "VIC0000"


def test_flatten_extracts_numeric_features() -> None:
    rows = _synthetic_rows(n=4)
    features, targets, asset_ids = flatten_training_rows(rows)
    assert len(features) == 4
    assert len(targets) == 4
    assert len(asset_ids) == 4
    assert all(isinstance(t, int) for t in targets)


def test_flatten_excludes_raw_string_categorical_fields() -> None:
    rows = _synthetic_rows(n=4)
    features, _, _ = flatten_training_rows(rows)
    excluded = {
        "industry", "business_type", "postcode", "lga_code", "lga_name",
        "station_id", "risk_band", "baseline_trigger_status",
    }
    for f in features:
        assert excluded.isdisjoint(f.keys())


def test_flatten_converts_booleans_to_floats() -> None:
    rows = _synthetic_rows(n=4)
    features, _, _ = flatten_training_rows(rows)
    for f in features:
        assert f["has_lga_assignment"] in (0.0, 1.0)


def test_flatten_preserves_deterministic_feature_order() -> None:
    rows = _synthetic_rows(n=4)
    features_a, _, _ = flatten_training_rows(rows)
    features_b, _, _ = flatten_training_rows(rows)
    assert list(features_a[0].keys()) == list(features_b[0].keys())
    assert list(features_a[0].keys()) == sorted(features_a[0].keys())


def test_flatten_raises_when_no_numeric_features() -> None:
    rows = [
        {
            "asset_id": "VIC0001",
            "as_of_date": date(2025, 12, 31),
            "feature_version": DEFAULT_FEATURE_VERSION,
            "target_extreme_rainfall_event": False,
            "engineered_features_json": {"industry": "retail", "business_type": "shop"},
        }
    ]
    with pytest.raises(ValueError, match="No usable numeric features"):
        flatten_training_rows(rows)


def test_flatten_raises_for_empty_rows() -> None:
    with pytest.raises(ValueError):
        flatten_training_rows([])


def test_matrices_split_is_deterministic_and_row_order_independent() -> None:
    rows = _synthetic_rows(n=100)
    features, targets, asset_ids = flatten_training_rows(rows)
    feature_names = list(features[0].keys())
    a = build_train_test_matrices(features, targets, asset_ids, feature_names)
    # Reverse the order of inputs; the split per asset_id must remain the same
    rev_features = list(reversed(features))
    rev_targets = list(reversed(targets))
    rev_asset_ids = list(reversed(asset_ids))
    b = build_train_test_matrices(rev_features, rev_targets, rev_asset_ids, feature_names)
    assert sorted(a["train_asset_ids"]) == sorted(b["train_asset_ids"])
    assert sorted(a["test_asset_ids"]) == sorted(b["test_asset_ids"])


def test_matrices_train_plus_test_equals_input() -> None:
    rows = _synthetic_rows(n=100)
    features, targets, asset_ids = flatten_training_rows(rows)
    feature_names = list(features[0].keys())
    m = build_train_test_matrices(features, targets, asset_ids, feature_names)
    assert m["X_train"].shape[0] + m["X_test"].shape[0] == 100
    assert m["X_train"].shape[1] == len(feature_names)


def test_scale_pos_weight_returns_neg_over_pos() -> None:
    targets = [1] * 25 + [0] * 75
    assert calculate_scale_pos_weight(targets) == 3.0


def test_scale_pos_weight_rejects_no_positives() -> None:
    with pytest.raises(ValueError, match="no positive"):
        calculate_scale_pos_weight([0] * 10)


def test_scale_pos_weight_rejects_no_negatives() -> None:
    with pytest.raises(ValueError, match="no negative"):
        calculate_scale_pos_weight([1] * 10)


def test_train_lightgbm_model_on_small_two_class_dataset() -> None:
    rows = _synthetic_rows(n=200)
    features, targets, asset_ids = flatten_training_rows(rows)
    feature_names = list(features[0].keys())
    matrices = build_train_test_matrices(features, targets, asset_ids, feature_names)
    params = {
        "objective": "binary",
        "n_estimators": 20,
        "num_leaves": 8,
        "random_state": 42,
        "verbose": -1,
    }
    model = train_lightgbm_model(matrices["X_train"], matrices["y_train"], params)
    assert hasattr(model, "predict_proba")
    assert hasattr(model, "booster_")
    probs = model.predict_proba(matrices["X_test"])[:, 1]
    assert probs.shape == (matrices["X_test"].shape[0],)


def test_save_training_artifacts_writes_all_required_files(tmp_path: Path) -> None:
    rows = _synthetic_rows(n=200)
    features, targets, asset_ids = flatten_training_rows(rows)
    feature_names = list(features[0].keys())
    matrices = build_train_test_matrices(features, targets, asset_ids, feature_names)
    model = train_lightgbm_model(
        matrices["X_train"],
        matrices["y_train"],
        {"objective": "binary", "n_estimators": 10, "num_leaves": 4, "verbose": -1},
    )
    metadata = {
        "model_name": "test_lgbm",
        "model_version": "v1",
        "as_of_date": "2025-12-31",
        "feature_version": DEFAULT_FEATURE_VERSION,
    }
    metrics = {"roc_auc": 0.9, "pr_auc": 0.5}
    importance = [
        {"feature": "rainfall_3d_mm", "importance_gain": 100.0, "importance_split": 10}
    ]
    paths = save_training_artifacts(
        model, metadata, metrics, feature_names, importance, tmp_path / "artifacts"
    )
    for key in ("model", "metadata", "feature_names", "metrics", "feature_importance"):
        assert paths[key].exists(), f"missing artefact {key}"
    # Round-trip the pickle
    with paths["model"].open("rb") as fh:
        loaded = pickle.load(fh)
    assert hasattr(loaded, "predict_proba")
    # Metrics JSON round-trip
    assert json.loads(paths["metrics"].read_text())["roc_auc"] == 0.9


class FakeSession:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = rows

    def execute(self, stmt: Any) -> Any:
        class _Row:
            def __init__(self, r: dict[str, Any]) -> None:
                self._t = (
                    r["asset_id"],
                    r["as_of_date"],
                    r["feature_version"],
                    r["target_extreme_rainfall_event"],
                    r["engineered_features_json"],
                )

            def __getitem__(self, i: int) -> Any:
                return self._t[i]

        class _Result:
            def __init__(self, rows: list[Any]) -> None:
                self._rows = rows

            def all(self) -> list[Any]:
                return self._rows

        return _Result([_Row(r) for r in self._rows])


def test_run_training_returns_canonical_summary(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(training_module, "log_training_run_to_mlflow", lambda **kw: {
        "mlflow_logged": False,
        "mlflow_run_id": None,
        "mlflow_tracking_uri": "file:./mlruns",
        "warning": "mlflow disabled for unit test",
    })
    rows = _synthetic_rows(n=200)
    session = FakeSession(rows)
    summary = run_lightgbm_training(
        session,
        as_of_date=date(2025, 12, 31),
        output_dir=tmp_path / "artifacts",
        log_to_mlflow=True,
    )
    assert summary["model_name"] == DEFAULT_MODEL_NAME
    assert summary["model_version"] == DEFAULT_MODEL_VERSION
    assert summary["train_row_count"] + summary["test_row_count"] == 200
    assert summary["feature_count"] > 0
    assert 0 <= summary["positive_rate"] <= 1
    assert (tmp_path / "artifacts" / "model.pkl").exists()
    assert (tmp_path / "artifacts" / "metrics.json").exists()


def test_run_training_raises_when_no_rows(monkeypatch: pytest.MonkeyPatch) -> None:
    session = FakeSession([])
    with pytest.raises(ValueError, match="No model_training_data"):
        run_lightgbm_training(session)


def test_run_training_raises_when_one_class(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    rows = _synthetic_rows(n=50)
    for r in rows:
        r["target_extreme_rainfall_event"] = False
    session = FakeSession(rows)
    with pytest.raises(ValueError, match="both classes"):
        run_lightgbm_training(session, output_dir=tmp_path / "artifacts", log_to_mlflow=False)
