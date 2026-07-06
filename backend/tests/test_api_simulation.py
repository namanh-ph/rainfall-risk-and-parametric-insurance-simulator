"""Tests for the simulation POST endpoints"""

from __future__ import annotations

from datetime import date
from typing import Any

import pytest
from fastapi.testclient import TestClient

from src.api import routes_simulation
from src.main import app

client = TestClient(app)


def _payout_summary(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "simulation_id": "API_2025_BASELINE",
        "simulation_name": "API 2025 baseline simulation",
        "as_of_date": date(2025, 12, 31),
        "coverage_multiplier": 1.0,
        "assets_considered": 5000,
        "feature_records_available": 5000,
        "payout_records_generated": 5000,
        "payout_records_inserted": 5000,
        "triggered_assets": 25,
        "not_triggered_assets": 4975,
        "total_coverage_limit": 1_500_000_000.0,
        "total_estimated_payout": 1_250_000.0,
        "average_payout_rate": 0.01,
        "replace_existing": True,
    }
    base.update(overrides)
    return base


def _sensitivity_scenarios() -> list[dict[str, Any]]:
    return [
        {
            "simulation_id": "DEFAULT_2025_BASELINE",
            "simulation_name": "Default 2025 baseline parametric payout simulation",
            "threshold_config": [],
            "coverage_multiplier": 1.0,
            "payout_records_generated": 5000,
            "payout_records_inserted": 5000,
            "summary": {
                "asset_count": 5000,
                "triggered_assets": 25,
                "not_triggered_assets": 4975,
                "trigger_rate": 0.005,
                "total_coverage_limit": 1_500_000_000.0,
                "total_estimated_payout": 1_250_000.0,
                "average_payout_rate": 0.01,
            },
        },
        {
            "simulation_id": "SWEEP_2025_T020",
            "simulation_name": "2025 very-sensitive threshold sensitivity simulation",
            "threshold_config": [],
            "coverage_multiplier": 1.0,
            "payout_records_generated": 5000,
            "payout_records_inserted": 5000,
            "summary": {
                "asset_count": 5000,
                "triggered_assets": 1500,
                "not_triggered_assets": 3500,
                "trigger_rate": 0.3,
                "total_coverage_limit": 1_500_000_000.0,
                "total_estimated_payout": 175_000_000.0,
                "average_payout_rate": 0.12,
            },
        },
    ]


def _threshold_summary() -> dict[str, Any]:
    return {
        "as_of_date": date(2025, 12, 31),
        "scenario_count": 2,
        "scenarios": _sensitivity_scenarios(),
        "replace_existing": True,
    }


def _combined_summary() -> dict[str, Any]:
    return {
        "as_of_date": date(2025, 12, 31),
        "threshold_sensitivity": _threshold_summary(),
        "coverage_multiplier_sensitivity": _threshold_summary(),
        "replace_existing": True,
    }


def test_simulate_payout_route_exists(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        routes_simulation, "run_payout_simulation", lambda *a, **kw: _payout_summary()
    )
    response = client.post(
        "/api/v1/simulate/payout",
        json={"as_of_date": "2025-12-31", "simulation_id": "API_2025_BASELINE"},
    )
    assert response.status_code == 200


def test_threshold_sensitivity_route_exists(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        routes_simulation, "run_threshold_sensitivity", lambda *a, **kw: _threshold_summary()
    )
    response = client.post(
        "/api/v1/simulate/threshold-sensitivity",
        json={"mode": "thresholds"},
    )
    assert response.status_code == 200


def test_simulate_payout_calls_service_with_request_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    def _stub(db: Any, **kwargs: Any) -> dict[str, Any]:
        captured.update(kwargs)
        return _payout_summary()

    monkeypatch.setattr(routes_simulation, "run_payout_simulation", _stub)
    response = client.post(
        "/api/v1/simulate/payout",
        json={
            "as_of_date": "2025-12-31",
            "simulation_id": "API_X",
            "simulation_name": "API X",
            "coverage_multiplier": 1.25,
            "asset_ids": ["VIC0001", "VIC0002"],
            "replace_existing": True,
            "include_risk_band": False,
        },
    )
    assert response.status_code == 200
    assert captured["simulation_id"] == "API_X"
    assert captured["coverage_multiplier"] == 1.25
    assert captured["asset_ids"] == ["VIC0001", "VIC0002"]
    assert captured["include_risk_band"] is False
    assert captured["as_of_date"] == date(2025, 12, 31)


def test_simulate_payout_returns_canonical_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        routes_simulation, "run_payout_simulation", lambda *a, **kw: _payout_summary()
    )
    payload = client.post(
        "/api/v1/simulate/payout",
        json={"as_of_date": "2025-12-31"},
    ).json()
    for key in (
        "simulation_id",
        "simulation_name",
        "as_of_date",
        "coverage_multiplier",
        "assets_considered",
        "feature_records_available",
        "payout_records_generated",
        "payout_records_inserted",
        "triggered_assets",
        "not_triggered_assets",
        "total_coverage_limit",
        "total_estimated_payout",
        "average_payout_rate",
        "replace_existing",
    ):
        assert key in payload


def test_simulate_payout_rejects_invalid_coverage_multiplier() -> None:
    response = client.post(
        "/api/v1/simulate/payout",
        json={"coverage_multiplier": -1.0},
    )
    assert response.status_code == 422  # Pydantic validation error


def test_simulate_payout_returns_400_on_service_value_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _raises(*a: Any, **kw: Any) -> Any:
        raise ValueError("No rainfall_features for as_of_date=2025-12-31")

    monkeypatch.setattr(routes_simulation, "run_payout_simulation", _raises)
    response = client.post("/api/v1/simulate/payout", json={})
    assert response.status_code == 400


def test_threshold_sensitivity_defaults_to_thresholds_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called: dict[str, bool] = {}

    def _stub(*a: Any, **kw: Any) -> dict[str, Any]:
        called["thresholds"] = True
        return _threshold_summary()

    monkeypatch.setattr(routes_simulation, "run_threshold_sensitivity", _stub)
    response = client.post("/api/v1/simulate/threshold-sensitivity", json={})
    assert response.status_code == 200
    assert called["thresholds"] is True
    assert response.json()["mode"] == "thresholds"


def test_threshold_sensitivity_supports_coverage_multipliers_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called: dict[str, bool] = {}

    def _stub(*a: Any, **kw: Any) -> dict[str, Any]:
        called["coverage_multipliers"] = True
        return _threshold_summary()

    monkeypatch.setattr(routes_simulation, "run_coverage_multiplier_sensitivity", _stub)
    response = client.post(
        "/api/v1/simulate/threshold-sensitivity",
        json={"mode": "coverage_multipliers"},
    )
    assert response.status_code == 200
    assert called["coverage_multipliers"] is True


def test_threshold_sensitivity_supports_combined_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        routes_simulation, "run_combined_sensitivity", lambda *a, **kw: _combined_summary()
    )
    response = client.post(
        "/api/v1/simulate/threshold-sensitivity",
        json={"mode": "combined"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["mode"] == "combined"
    # combined flattens threshold + coverage scenarios → 2 + 2 = 4
    assert payload["scenario_count"] == 4
    assert len(payload["scenarios"]) == 4


def test_threshold_sensitivity_rejects_invalid_mode() -> None:
    response = client.post(
        "/api/v1/simulate/threshold-sensitivity",
        json={"mode": "all_the_things"},
    )
    assert response.status_code == 422


def test_threshold_sensitivity_returns_scenario_summaries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        routes_simulation, "run_threshold_sensitivity", lambda *a, **kw: _threshold_summary()
    )
    payload = client.post(
        "/api/v1/simulate/threshold-sensitivity", json={}
    ).json()
    assert payload["scenario_count"] == 2
    first = payload["scenarios"][0]
    for key in (
        "simulation_id",
        "simulation_name",
        "coverage_multiplier",
        "payout_records_generated",
        "payout_records_inserted",
        "asset_count",
        "triggered_assets",
        "not_triggered_assets",
        "trigger_rate",
        "total_coverage_limit",
        "total_estimated_payout",
        "average_payout_rate",
    ):
        assert key in first


def test_simulation_endpoints_do_not_call_other_pipelines(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """POST /simulate/* may call payout/sensitivity service functions (allowed),
    but must not invoke ingestion / matching / features / scoring / training / prediction"""
    called: list[str] = []

    def _trip(name: str) -> Any:
        def _f(*a: Any, **kw: Any) -> Any:
            called.append(name)
            raise AssertionError(f"forbidden call to {name} from API")
        return _f

    monkeypatch.setattr("src.ingestion.assets.load_static_assets_to_db", _trip("load_assets"))
    monkeypatch.setattr(
        "src.geospatial.station_matching.run_asset_station_matching", _trip("match")
    )
    monkeypatch.setattr("src.geospatial.lga_join.run_asset_lga_assignment", _trip("lga"))
    monkeypatch.setattr(
        "src.features.rainfall_features.run_rainfall_feature_generation", _trip("features")
    )
    monkeypatch.setattr("src.risk.scoring.run_asset_risk_scoring", _trip("risk"))
    monkeypatch.setattr("src.ml.training.run_lightgbm_training", _trip("train"))
    monkeypatch.setattr("src.ml.prediction.run_batch_prediction", _trip("predict"))

    # Allowed service functions: replace with stubs that return canned summaries
    monkeypatch.setattr(
        routes_simulation, "run_payout_simulation", lambda *a, **kw: _payout_summary()
    )
    monkeypatch.setattr(
        routes_simulation,
        "run_threshold_sensitivity",
        lambda *a, **kw: _threshold_summary(),
    )

    client.post("/api/v1/simulate/payout", json={})
    client.post("/api/v1/simulate/threshold-sensitivity", json={})
    assert called == []
