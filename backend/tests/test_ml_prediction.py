"""Tests for the batch prediction pipeline"""

from __future__ import annotations

import json
import math
import pickle
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from pydantic import ValidationError

from src.db.models import ModelPrediction
from src.ml.prediction import (
    align_features_to_model,
    build_model_prediction_records,
    calculate_prediction_ranks,
    flatten_prediction_rows,
    generate_prediction_probabilities,
    infer_top_risk_driver,
    load_feature_importance,
    load_model_artifacts,
    persist_model_predictions,
    validate_model_prediction_records,
)
from src.schemas.ml_prediction import ModelPredictionRecord


class _StubModel:
    """Returns predict_proba based on a fixed positive-class column"""

    def __init__(self, positive_probs: list[float]) -> None:
        self._proba = positive_probs

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        # Loop so callers get a 2-column array shaped like sklearn classifiers
        positives = np.asarray(self._proba[: X.shape[0]], dtype=float)
        return np.stack([1.0 - positives, positives], axis=1)


class _FakeResult:
    def __init__(self, rows: list[Any] | None = None) -> None:
        self._rows = rows or []

    def all(self) -> list[Any]:
        return self._rows


class FakeSession:
    def __init__(
        self,
        *,
        existing_keys: set[tuple[str, date, str, str]] | None = None,
    ) -> None:
        self.executes: list[Any] = []
        self.added: list[Any] = []
        self.committed = False
        self.rolled_back = False
        self._existing_keys = set(existing_keys or ())

    def execute(self, statement: Any, params: Any | None = None) -> _FakeResult:
        self.executes.append(statement)
        compiled = str(statement).lower()
        if compiled.startswith("delete"):
            return _FakeResult()
        if compiled.startswith("select") and "model_predictions" in compiled:
            return _FakeResult(rows=list(self._existing_keys))
        return _FakeResult()

    def add_all(self, objs: list[Any]) -> None:
        self.added.extend(objs)

    def commit(self) -> None:
        self.committed = True

    def rollback(self) -> None:
        self.rolled_back = True

    def close(self) -> None:  # pragma: no cover
        pass


def _write_artifacts(
    tmp_path: Path,
    *,
    model_name: str = "rainfall_risk_lgbm",
    model_version: str = "v1",
    feature_version: str = "rainfall_risk_features_v1",
    as_of_date: str = "2025-12-31",
    feature_names: list[str] | None = None,
    with_importance: bool = True,
    positive_probs: list[float] | None = None,
) -> Path:
    artefact_dir = tmp_path / f"{model_name}_{model_version}_{as_of_date}"
    artefact_dir.mkdir(parents=True, exist_ok=True)
    feature_names = feature_names or ["rainfall_percentile", "rainfall_3d_mm", "exposure_weight"]
    (artefact_dir / "feature_names.json").write_text(
        json.dumps(feature_names), encoding="utf-8"
    )
    (artefact_dir / "metadata.json").write_text(
        json.dumps(
            {
                "model_name": model_name,
                "model_version": model_version,
                "as_of_date": as_of_date,
                "feature_version": feature_version,
                "target_name": "target_extreme_rainfall_event",
            }
        ),
        encoding="utf-8",
    )
    model = _StubModel(positive_probs or [0.1, 0.5, 0.9])
    with (artefact_dir / "model.pkl").open("wb") as fh:
        pickle.dump(model, fh)
    if with_importance:
        with (artefact_dir / "feature_importance.csv").open("w", encoding="utf-8", newline="") as fh:
            fh.write("feature,importance_gain,importance_split\n")
            fh.write("rainfall_percentile,200.0,30\n")
            fh.write("rainfall_3d_mm,150.0,25\n")
            fh.write("exposure_weight,10.0,5\n")
    return artefact_dir


def test_load_model_artifacts_returns_components(tmp_path: Path) -> None:
    artefact_dir = _write_artifacts(tmp_path)
    artefacts = load_model_artifacts(artefact_dir)
    assert isinstance(artefacts["model"], _StubModel)
    assert artefacts["metadata"]["model_name"] == "rainfall_risk_lgbm"
    assert artefacts["feature_names"] == [
        "rainfall_percentile",
        "rainfall_3d_mm",
        "exposure_weight",
    ]
    assert len(artefacts["feature_importance"]) == 3


def test_load_model_artifacts_missing_dir_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_model_artifacts(tmp_path / "no_such_dir")


def test_load_model_artifacts_missing_required_file_raises(tmp_path: Path) -> None:
    artefact_dir = _write_artifacts(tmp_path)
    (artefact_dir / "model.pkl").unlink()
    with pytest.raises(FileNotFoundError):
        load_model_artifacts(artefact_dir)


def test_load_model_artifacts_metadata_conflict_raises(tmp_path: Path) -> None:
    artefact_dir = _write_artifacts(tmp_path)
    with pytest.raises(ValueError, match="model_version"):
        load_model_artifacts(
            artefact_dir,
            expected_model_version="v9",
        )


def test_load_model_artifacts_metadata_match_passes(tmp_path: Path) -> None:
    artefact_dir = _write_artifacts(tmp_path)
    artefacts = load_model_artifacts(
        artefact_dir,
        expected_model_name="rainfall_risk_lgbm",
        expected_model_version="v1",
        expected_feature_version="rainfall_risk_features_v1",
        expected_as_of_date=date(2025, 12, 31),
    )
    assert artefacts["metadata"]["feature_version"] == "rainfall_risk_features_v1"


def test_load_feature_importance_missing_file_returns_empty_list(tmp_path: Path) -> None:
    assert load_feature_importance(tmp_path / "missing.csv") == []


def _row(asset_id: str, **payload: Any) -> dict[str, Any]:
    return {
        "asset_id": asset_id,
        "as_of_date": date(2025, 12, 31),
        "feature_version": "rainfall_risk_features_v1",
        "target_extreme_rainfall_event": False,
        "engineered_features_json": payload,
    }


def test_flatten_excludes_raw_string_categoricals() -> None:
    rows = [
        _row("VIC0001", rainfall_30d_mm=12.0, industry="retail", business_type="shop"),
        _row("VIC0002", rainfall_30d_mm=15.0, industry="hospitality", business_type="cafe"),
    ]
    _feature_rows, asset_ids, feature_names = flatten_prediction_rows(rows)
    assert "industry" not in feature_names
    assert "business_type" not in feature_names
    assert "rainfall_30d_mm" in feature_names
    assert asset_ids == ["VIC0001", "VIC0002"]


def test_flatten_converts_booleans_to_floats() -> None:
    rows = [_row("VIC0001", rainfall_30d_mm=10.0, has_lga_assignment=True)]
    feature_rows, _, _ = flatten_prediction_rows(rows)
    assert feature_rows[0]["has_lga_assignment"] == 1.0


def test_flatten_does_not_include_target() -> None:
    rows = [_row("VIC0001", rainfall_30d_mm=10.0, target_extreme_rainfall_event=1.0)]
    _, _, feature_names = flatten_prediction_rows(rows)
    assert "target_extreme_rainfall_event" not in feature_names


def test_flatten_raises_on_empty_input() -> None:
    with pytest.raises(ValueError, match="empty row list"):
        flatten_prediction_rows([])


def test_flatten_drops_keys_with_string_values() -> None:
    rows = [
        _row("VIC0001", custom_field="abc", rainfall_30d_mm=10.0),
        _row("VIC0002", custom_field=1.0, rainfall_30d_mm=20.0),
    ]
    _, _, feature_names = flatten_prediction_rows(rows)
    assert "custom_field" not in feature_names
    assert "rainfall_30d_mm" in feature_names


def test_flatten_raises_when_no_numeric_features() -> None:
    rows = [_row("VIC0001", industry="retail", business_type="shop", postcode="x")]
    with pytest.raises(ValueError, match="No usable numeric features"):
        flatten_prediction_rows(rows)


def test_align_preserves_model_feature_order() -> None:
    feature_rows = [
        {"rainfall_3d_mm": 12.0, "rainfall_percentile": 0.8, "exposure_weight": 1.1},
        {"rainfall_3d_mm": 25.0, "rainfall_percentile": 0.99, "exposure_weight": 1.3},
    ]
    matrix, warnings = align_features_to_model(
        feature_rows, ["rainfall_percentile", "rainfall_3d_mm", "exposure_weight"]
    )
    assert matrix.shape == (2, 3)
    # Column 0 = rainfall_percentile
    assert matrix[0, 0] == 0.8
    assert matrix[1, 0] == 0.99
    assert warnings == []


def test_align_fills_missing_features_with_nan_and_warns() -> None:
    feature_rows = [{"rainfall_percentile": 0.8}]
    matrix, warnings = align_features_to_model(
        feature_rows, ["rainfall_percentile", "rainfall_3d_mm"]
    )
    assert math.isnan(matrix[0, 1])
    assert any("missing" in w for w in warnings)


def test_align_ignores_extra_features_and_warns() -> None:
    feature_rows = [
        {"rainfall_percentile": 0.8, "extra": 5.0},
    ]
    matrix, warnings = align_features_to_model(
        feature_rows, ["rainfall_percentile"]
    )
    assert matrix.shape == (1, 1)
    assert any("extra" in w for w in warnings)


def test_generate_probabilities_returns_values_in_unit_interval() -> None:
    model = _StubModel([0.1, 0.5, 0.9])
    probabilities = generate_prediction_probabilities(model, np.zeros((3, 2)))
    assert probabilities == [0.1, 0.5, 0.9]
    assert all(0 <= p <= 1 for p in probabilities)


def test_ranks_assigned_to_highest_probability_first() -> None:
    ranks = calculate_prediction_ranks(
        ["VIC0001", "VIC0002", "VIC0003"], [0.1, 0.9, 0.5]
    )
    assert ranks["VIC0002"] == 1
    assert ranks["VIC0003"] == 2
    assert ranks["VIC0001"] == 3


def test_ranks_break_ties_by_asset_id_ascending() -> None:
    ranks = calculate_prediction_ranks(
        ["VIC0003", "VIC0001", "VIC0002"], [0.5, 0.5, 0.5]
    )
    assert ranks["VIC0001"] == 1
    assert ranks["VIC0002"] == 2
    assert ranks["VIC0003"] == 3


def test_top_driver_picks_first_finite_feature_by_importance() -> None:
    importance = [
        {"feature": "rainfall_percentile", "importance_gain": 200.0, "importance_split": 30},
        {"feature": "rainfall_3d_mm", "importance_gain": 150.0, "importance_split": 25},
    ]
    feature_row = {"rainfall_percentile": 0.95, "rainfall_3d_mm": 12.0}
    assert (
        infer_top_risk_driver(feature_row, ["rainfall_percentile", "rainfall_3d_mm"], importance)
        == "rainfall_percentile"
    )


def test_top_driver_skips_nan_values_in_importance_order() -> None:
    importance = [
        {"feature": "rainfall_percentile", "importance_gain": 200.0, "importance_split": 30},
        {"feature": "rainfall_3d_mm", "importance_gain": 150.0, "importance_split": 25},
    ]
    feature_row = {"rainfall_percentile": float("nan"), "rainfall_3d_mm": 12.0}
    assert (
        infer_top_risk_driver(feature_row, ["rainfall_percentile", "rainfall_3d_mm"], importance)
        == "rainfall_3d_mm"
    )


def test_top_driver_falls_back_to_largest_absolute_value() -> None:
    feature_row = {"rainfall_3d_mm": 30.0, "exposure_weight": 1.1, "log_asset_value": 18.0}
    assert (
        infer_top_risk_driver(feature_row, ["exposure_weight", "rainfall_3d_mm", "log_asset_value"])
        == "rainfall_3d_mm"
    )


def test_top_driver_returns_none_when_no_finite_values() -> None:
    feature_row = {"rainfall_3d_mm": float("nan"), "exposure_weight": float("nan")}
    assert infer_top_risk_driver(feature_row, ["rainfall_3d_mm", "exposure_weight"]) is None


def test_build_records_canonical_fields() -> None:
    rows = [
        _row("VIC0001", rainfall_percentile=0.95, rainfall_3d_mm=20.0),
        _row("VIC0002", rainfall_percentile=0.4, rainfall_3d_mm=5.0),
    ]
    probabilities = [0.9, 0.1]
    ranks = calculate_prediction_ranks(["VIC0001", "VIC0002"], probabilities)
    records = build_model_prediction_records(
        rows=rows,
        probabilities=probabilities,
        ranks=ranks,
        model_name="rainfall_risk_lgbm",
        model_version="v1",
        as_of_date=date(2025, 12, 31),
        model_feature_names=["rainfall_percentile", "rainfall_3d_mm"],
        feature_importance=[
            {"feature": "rainfall_percentile", "importance_gain": 200.0, "importance_split": 30},
            {"feature": "rainfall_3d_mm", "importance_gain": 150.0, "importance_split": 25},
        ],
    )
    assert {r["asset_id"] for r in records} == {"VIC0001", "VIC0002"}
    assert records[0]["ml_risk_rank"] == 1
    assert records[0]["top_risk_driver"] == "rainfall_percentile"


def _good_record(asset_id: str = "VIC0001") -> dict[str, Any]:
    return {
        "asset_id": asset_id,
        "as_of_date": date(2025, 12, 31),
        "model_name": "rainfall_risk_lgbm",
        "model_version": "v1",
        "ml_risk_probability": 0.42,
        "ml_risk_rank": 1,
        "top_risk_driver": "rainfall_percentile",
    }


def test_schema_validates_good_record() -> None:
    rec = ModelPredictionRecord.model_validate(_good_record())
    assert rec.ml_risk_rank == 1


@pytest.mark.parametrize("prob", [-0.01, 1.01, 2.0])
def test_schema_rejects_invalid_probability(prob: float) -> None:
    bad = _good_record()
    bad["ml_risk_probability"] = prob
    with pytest.raises(ValidationError):
        ModelPredictionRecord.model_validate(bad)


@pytest.mark.parametrize("rank", [0, -1, -100])
def test_schema_rejects_invalid_rank(rank: int) -> None:
    bad = _good_record()
    bad["ml_risk_rank"] = rank
    with pytest.raises(ValidationError):
        ModelPredictionRecord.model_validate(bad)


def test_validate_accepts_unique_records() -> None:
    out = validate_model_prediction_records(
        [_good_record("VIC0001"), _good_record("VIC0002")]
    )
    assert len(out) == 2


def test_validate_rejects_duplicate_quadruplet() -> None:
    with pytest.raises(ValueError, match="Duplicate"):
        validate_model_prediction_records(
            [_good_record("VIC0001"), _good_record("VIC0001")]
        )


def test_persist_inserts_when_replace_existing_true() -> None:
    rec1 = _good_record("VIC0001")
    rec2 = _good_record("VIC0002")
    rec2["ml_risk_rank"] = 2
    session = FakeSession()
    n = persist_model_predictions([rec1, rec2], session, replace_existing=True)
    assert n == 2
    assert all(isinstance(o, ModelPrediction) for o in session.added)
    assert session.committed is True


def test_persist_replace_existing_issues_delete_first() -> None:
    rec = _good_record("VIC0001")
    session = FakeSession()
    persist_model_predictions([rec], session, replace_existing=True)
    deletes = [s for s in session.executes if str(s).lower().startswith("delete")]
    assert len(deletes) == 1


def test_persist_skips_existing_when_replace_existing_false() -> None:
    rec1 = _good_record("VIC0001")
    rec2 = _good_record("VIC0002")
    rec2["ml_risk_rank"] = 2
    session = FakeSession(
        existing_keys={
            ("VIC0001", date(2025, 12, 31), "rainfall_risk_lgbm", "v1"),
        }
    )
    n = persist_model_predictions([rec1, rec2], session, replace_existing=False)
    assert n == 1
    assert {o.asset_id for o in session.added} == {"VIC0002"}


def test_persist_validates_before_insert() -> None:
    bad = _good_record()
    bad["ml_risk_probability"] = 1.5
    session = FakeSession()
    with pytest.raises(ValidationError):
        persist_model_predictions([bad], session)
    assert session.committed is False


def test_persist_rolls_back_on_failure() -> None:
    records = [_good_record("VIC0001")]

    class Boom(FakeSession):
        def add_all(self, objs: list[Any]) -> None:
            raise RuntimeError("boom")

    session = Boom()
    with pytest.raises(RuntimeError):
        persist_model_predictions(records, session)
    assert session.rolled_back is True
    assert session.committed is False


def test_persist_returns_zero_for_empty_input() -> None:
    session = FakeSession()
    assert persist_model_predictions([], session) == 0
    assert session.committed is False
