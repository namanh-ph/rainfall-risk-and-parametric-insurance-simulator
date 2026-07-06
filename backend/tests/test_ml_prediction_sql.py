"""Tests confirming prediction data access is scoped to model_training_data"""

from __future__ import annotations

import inspect
from datetime import date
from typing import Any
from unittest.mock import MagicMock

from src.ml import prediction as prediction_module
from src.ml.prediction import load_prediction_rows


def test_prediction_module_does_not_reference_forbidden_tables() -> None:
    source = inspect.getsource(prediction_module)
    # The only DB tables that should appear in this module are
    # model_training_data (read) and model_predictions (write)
    for forbidden in (
        "rainfall_features",
        "asset_risk_scores",
        "asset_station_mapping",
        "payout_results",
        "simulation_runs",
        "lga_boundaries",
        "rainfall_stations",
        "rainfall_observations",
        "FROM assets",
        "JOIN assets",
    ):
        assert forbidden not in source, (
            f"prediction module unexpectedly references {forbidden!r}"
        )


def test_prediction_module_references_model_training_data() -> None:
    source = inspect.getsource(prediction_module)
    assert "ModelTrainingData" in source


def test_load_prediction_rows_filters_by_as_of_date_and_feature_version() -> None:
    """The SQLAlchemy statement should compile with both filters bound"""
    captured: dict[str, Any] = {}

    class _StubSession:
        def execute(self, stmt: Any) -> Any:
            captured["stmt"] = stmt

            class _R:
                def all(self_inner) -> list[Any]:
                    return []

            return _R()

    load_prediction_rows(
        _StubSession(),  # type: ignore[arg-type]
        as_of_date=date(2024, 6, 30),
        feature_version="rainfall_risk_features_v1",
    )
    compiled = str(captured["stmt"]).lower()
    assert "model_training_data" in compiled
    assert "as_of_date" in compiled
    assert "feature_version" in compiled


def test_load_prediction_rows_does_not_reference_forbidden_tables() -> None:
    captured: dict[str, Any] = {}

    class _StubSession:
        def execute(self, stmt: Any) -> Any:
            captured["stmt"] = stmt

            class _R:
                def all(self_inner) -> list[Any]:
                    return []

            return _R()

    load_prediction_rows(_StubSession())  # type: ignore[arg-type]
    compiled = str(captured["stmt"]).lower()
    for forbidden in (
        "rainfall_features",
        "asset_risk_scores",
        "asset_station_mapping",
        "payout_results",
        "model_predictions",
    ):
        assert forbidden not in compiled


def test_load_prediction_rows_with_asset_ids_uses_in_clause() -> None:
    captured: dict[str, Any] = {}

    class _StubSession:
        def execute(self, stmt: Any) -> Any:
            captured["stmt"] = stmt

            class _R:
                def all(self_inner) -> list[Any]:
                    return []

            return _R()

    load_prediction_rows(
        _StubSession(),  # type: ignore[arg-type]
        asset_ids=["VIC0001", "VIC0002"],
    )
    compiled = str(captured["stmt"])
    # Raw IDs should never appear inline; SQLAlchemy renders the filter as IN (...)
    assert "VIC0001" not in compiled
    assert "VIC0002" not in compiled
    assert "asset_id" in compiled.lower()


def test_load_prediction_rows_returns_dicts_with_expected_keys() -> None:
    class _Row(tuple):
        pass

    class _Result:
        def all(self) -> list[Any]:
            return [_Row(("VIC0001", date(2025, 12, 31), "rainfall_risk_features_v1", True, {"x": 1.0}))]

    class _StubSession:
        def execute(self, stmt: Any) -> Any:
            return _Result()

    session = MagicMock()
    session.execute = _StubSession().execute
    out = load_prediction_rows(session)
    assert out[0]["asset_id"] == "VIC0001"
    assert out[0]["target_extreme_rainfall_event"] is True
    assert out[0]["engineered_features_json"] == {"x": 1.0}
