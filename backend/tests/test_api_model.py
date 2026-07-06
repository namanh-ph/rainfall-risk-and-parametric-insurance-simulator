"""Tests for the model metadata and prediction endpoints"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from src.api import routes_model
from src.main import app

client = TestClient(app)


def _metadata_dict() -> dict[str, Any]:
    return {
        "model_name": "rainfall_risk_lgbm",
        "model_version": "v1",
        "as_of_date": "2025-12-31",
        "feature_version": "rainfall_risk_features_v1",
        "target_name": "target_extreme_rainfall_event",
        "artifact_path": "backend/artifacts/models/rainfall_risk_lgbm_v1_2025-12-31",
        "feature_count": 48,
        "train_row_count": 4000,
        "test_row_count": 1000,
        "positive_count": 125,
        "negative_count": 4875,
        "positive_rate": 0.025,
        "mlflow_logged": True,
        "mlflow_run_id": "abc123",
        "created_at": "2026-05-12T10:00:00+00:00",
    }


def _metrics_dict() -> dict[str, Any]:
    return {
        "roc_auc": 0.83,
        "pr_auc": 0.21,
        "accuracy": 0.95,
        "precision": 0.18,
        "recall": 0.72,
        "f1": 0.288,
        "precision_at_top_10_pct": 0.18,
        "recall_at_top_10_pct": 0.72,
        "lift_at_top_10_pct": 7.2,
        "positive_rate": 0.025,
        "train_row_count": 4000,
        "test_row_count": 1000,
        "feature_count": 48,
    }


def _prediction_list_row(asset_id: str = "VIC0001", rank: int = 1) -> dict[str, Any]:
    return {
        "asset_id": asset_id,
        "business_type": "warehouse",
        "industry": "logistics",
        "postcode": "Dandenong",
        "lga_code": "LGA21890c",
        "lga_name": "Greater Dandenong",
        "risk_score": 80.0,
        "risk_band": "Severe",
        "ml_risk_probability": 0.81,
        "ml_risk_rank": rank,
        "top_risk_driver": "rainfall_percentile",
        "as_of_date": date(2025, 12, 31),
        "model_name": "rainfall_risk_lgbm",
        "model_version": "v1",
    }


def _prediction_detail_row(asset_id: str = "VIC0001") -> dict[str, Any]:
    return {
        **_prediction_list_row(asset_id),
        "rainfall_3d_mm": 25.5,
        "rainfall_percentile": 0.94,
        "extreme_rainfall_flag": False,
    }


@pytest.fixture(autouse=True)
def _no_real_db(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(routes_model, "_fetch_prediction_count", lambda *a, **kw: 0)
    monkeypatch.setattr(routes_model, "_fetch_prediction_list", lambda *a, **kw: ([], 0))
    monkeypatch.setattr(routes_model, "_asset_exists", lambda *a, **kw: False)
    monkeypatch.setattr(routes_model, "_fetch_prediction_detail", lambda *a, **kw: None)


def test_model_metadata_route_exists() -> None:
    response = client.get("/api/v1/model/metadata")
    assert response.status_code == 200


def test_model_metadata_reads_temp_artefact_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "metadata.json").write_text(json.dumps(_metadata_dict()))
    (tmp_path / "metrics.json").write_text(json.dumps(_metrics_dict()))
    monkeypatch.setattr(routes_model, "_fetch_prediction_count", lambda *a, **kw: 5000)

    response = client.get(f"/api/v1/model/metadata?artifact_dir={tmp_path}")
    assert response.status_code == 200
    payload = response.json()
    assert payload["model_name"] == "rainfall_risk_lgbm"
    assert payload["feature_count"] == 48
    assert payload["metrics"]["roc_auc"] == 0.83
    assert payload["prediction_count"] == 5000
    assert payload["mlflow_run_id"] == "abc123"


def test_model_metadata_returns_200_when_artifact_files_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(routes_model, "_fetch_prediction_count", lambda *a, **kw: 0)
    response = client.get(f"/api/v1/model/metadata?artifact_dir={tmp_path / 'missing'}")
    assert response.status_code == 200
    payload = response.json()
    # Fields fall back to query-param defaults; metadata-only fields are null
    assert payload["model_name"] == "rainfall_risk_lgbm"
    assert payload["model_version"] == "v1"
    assert payload["feature_count"] is None
    assert payload["metrics"] is None
    assert payload["prediction_count"] == 0


def test_model_metadata_includes_prediction_count(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(routes_model, "_fetch_prediction_count", lambda *a, **kw: 4321)
    response = client.get("/api/v1/model/metadata")
    assert response.status_code == 200
    assert response.json()["prediction_count"] == 4321


def test_model_predictions_list_route_exists() -> None:
    response = client.get("/api/v1/model/predictions")
    assert response.status_code == 200


def test_model_predictions_returns_pagination_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        routes_model,
        "_fetch_prediction_list",
        lambda *a, **kw: (
            [_prediction_list_row("VIC0001", 1), _prediction_list_row("VIC0002", 2)],
            5000,
        ),
    )
    payload = client.get("/api/v1/model/predictions?limit=10").json()
    assert payload["pagination"] == {
        "limit": 10,
        "offset": 0,
        "total": 5000,
        "returned": 2,
    }
    assert len(payload["items"]) == 2


def test_model_predictions_supports_risk_band_filter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    def _stub(*a: Any, **kw: Any) -> tuple[list[dict], int]:
        captured.update(kw)
        return ([], 0)

    monkeypatch.setattr(routes_model, "_fetch_prediction_list", _stub)
    response = client.get("/api/v1/model/predictions?risk_band=Severe")
    assert response.status_code == 200
    assert captured["risk_band"] == "Severe"


def test_model_predictions_rejects_invalid_risk_band() -> None:
    response = client.get("/api/v1/model/predictions?risk_band=Critical")
    assert response.status_code == 400


def test_model_predictions_supports_allowed_sort_by() -> None:
    for field in (
        "ml_risk_rank",
        "ml_risk_probability",
        "risk_score",
        "asset_value",
        "coverage_limit",
    ):
        response = client.get(f"/api/v1/model/predictions?sort_by={field}")
        assert response.status_code == 200, f"sort_by={field}"


def test_model_predictions_rejects_invalid_sort_by() -> None:
    response = client.get("/api/v1/model/predictions?sort_by=evil_column")
    assert response.status_code == 400


def test_model_prediction_detail_returns_prediction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(routes_model, "_asset_exists", lambda *a, **kw: True)
    monkeypatch.setattr(
        routes_model, "_fetch_prediction_detail", lambda *a, **kw: _prediction_detail_row()
    )
    response = client.get("/api/v1/model/predictions/VIC0001")
    assert response.status_code == 200
    payload = response.json()
    assert payload["asset_id"] == "VIC0001"
    assert payload["rainfall_3d_mm"] == 25.5
    assert payload["top_risk_driver"] == "rainfall_percentile"


def test_model_prediction_detail_returns_404_for_missing_asset() -> None:
    response = client.get("/api/v1/model/predictions/VIC9999")
    assert response.status_code == 404


def test_model_prediction_detail_returns_404_for_missing_prediction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(routes_model, "_asset_exists", lambda *a, **kw: True)
    # _fetch_prediction_detail default returns None
    response = client.get("/api/v1/model/predictions/VIC0001")
    assert response.status_code == 404


def test_model_endpoints_do_not_train_or_predict(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called: list[str] = []

    def _trip(name: str) -> Any:
        def _f(*a: Any, **kw: Any) -> Any:
            called.append(name)
            raise AssertionError(f"forbidden call to {name} from API")
        return _f

    monkeypatch.setattr("src.ml.training.run_lightgbm_training", _trip("train"))
    monkeypatch.setattr("src.ml.prediction.run_batch_prediction", _trip("predict"))
    monkeypatch.setattr(
        "src.ml.dataset.run_model_training_data_build", _trip("build_training_data")
    )

    for path in (
        "/api/v1/model/metadata",
        "/api/v1/model/predictions",
        "/api/v1/model/predictions/VIC0001",
    ):
        client.get(path)
    assert called == []
