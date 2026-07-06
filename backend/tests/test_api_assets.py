"""Tests for the asset HTTP endpoints."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient

from src.api import routes_assets
from src.main import app

client = TestClient(app)


def _list_row(asset_id: str = "VIC0001", **overrides: Any) -> dict[str, Any]:
    row: dict[str, Any] = {
        "asset_id": asset_id,
        "business_type": "cafe",
        "industry": "hospitality",
        "postcode": "Richmond",
        "latitude": -37.82,
        "longitude": 144.99,
        "asset_value": 750_000.0,
        "annual_revenue": 380_000.0,
        "coverage_limit": 80_000.0,
        "lga_code": "LGA20660",
        "lga_name": "Melbourne",
        "risk_score": 42.5,
        "risk_band": "Medium",
        "rainfall_3d_mm": 12.5,
        "station_id": "086282",
        "station_distance_km": 4.5,
        "ml_risk_probability": 0.123,
        "ml_risk_rank": 11,
    }
    row.update(overrides)
    return row


def _detail_row(**overrides: Any) -> dict[str, Any]:
    row: dict[str, Any] = {
        **_list_row(),
        "rainfall_1d_mm": 2.5,
        "rainfall_7d_mm": 25.0,
        "rainfall_30d_mm": 100.0,
        "rainfall_percentile": 0.72,
        "extreme_rainfall_flag": False,
        "station_name": "Melbourne Olympic Park",
        "station_confidence_weight": 0.955,
        "top_risk_driver": "rainfall_3d_mm",
    }
    row.update(overrides)
    return row


def _risk_row(**overrides: Any) -> dict[str, Any]:
    row: dict[str, Any] = {
        "asset_id": "VIC0001",
        "as_of_date": "2025-12-31",
        "rainfall_extreme_score": 60.0,
        "exposure_weight": 1.05,
        "vulnerability_weight": 1.20,
        "station_confidence_weight": 0.955,
        "raw_score": 60.0 * 1.05 * 1.20 * 0.955,
        "risk_score": 72.13,
        "risk_band": "High",
    }
    row.update(overrides)
    return row


def _rainfall_row(**overrides: Any) -> dict[str, Any]:
    row: dict[str, Any] = {
        "asset_id": "VIC0001",
        "station_id": "086282",
        "as_of_date": "2025-12-31",
        "rainfall_1d_mm": 2.5,
        "rainfall_3d_mm": 12.5,
        "rainfall_7d_mm": 25.0,
        "rainfall_30d_mm": 100.0,
        "rainfall_p95_station": 7.5,
        "rainfall_p99_station": 14.0,
        "rainfall_percentile": 0.72,
        "max_365d_rainfall_mm": 80.0,
        "days_above_p95_365d": 18,
        "extreme_rainfall_flag": False,
    }
    row.update(overrides)
    return row


def _station_row(**overrides: Any) -> dict[str, Any]:
    row: dict[str, Any] = {
        "asset_id": "VIC0001",
        "station_id": "086282",
        "station_name": "Melbourne Olympic Park",
        "latitude": -37.83,
        "longitude": 144.98,
        "station_distance_km": 4.5,
        "station_confidence_weight": 0.955,
        "matched_at": datetime(2026, 5, 1, tzinfo=UTC),
        "data_source": "bom",
    }
    row.update(overrides)
    return row


@pytest.fixture(autouse=True)
def _no_real_db(monkeypatch: pytest.MonkeyPatch) -> None:
    """Default to empty results unless individual tests override."""
    monkeypatch.setattr(routes_assets, "_fetch_asset_list", lambda *a, **kw: ([], 0))
    monkeypatch.setattr(routes_assets, "_fetch_asset_detail", lambda *a, **kw: None)
    monkeypatch.setattr(routes_assets, "_asset_exists", lambda *a, **kw: False)
    monkeypatch.setattr(routes_assets, "_fetch_asset_risk", lambda *a, **kw: None)
    monkeypatch.setattr(routes_assets, "_fetch_asset_rainfall", lambda *a, **kw: None)
    monkeypatch.setattr(routes_assets, "_fetch_asset_station", lambda *a, **kw: None)


def test_assets_list_route_registered() -> None:
    response = client.get("/assets")
    assert response.status_code == 200


def test_assets_list_returns_pagination_metadata(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        routes_assets,
        "_fetch_asset_list",
        lambda *a, **kw: ([_list_row("VIC0001"), _list_row("VIC0002")], 2),
    )
    payload = client.get("/assets?limit=10&offset=0").json()
    assert payload["pagination"] == {"limit": 10, "offset": 0, "total": 2, "returned": 2}


def test_assets_list_respects_limit_and_offset(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    def _stub(*args: Any, **kwargs: Any) -> tuple[list[dict], int]:
        captured.update(kwargs)
        return ([], 0)

    monkeypatch.setattr(routes_assets, "_fetch_asset_list", _stub)
    client.get("/assets?limit=25&offset=50")
    assert captured["limit"] == 25
    assert captured["offset"] == 50


def test_assets_list_supports_industry_filter(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    def _stub(*args: Any, **kwargs: Any) -> tuple[list[dict], int]:
        captured.update(kwargs)
        return ([], 0)

    monkeypatch.setattr(routes_assets, "_fetch_asset_list", _stub)
    client.get("/assets?industry=hospitality")
    assert captured["industry"] == "hospitality"


def test_assets_list_supports_risk_band_filter(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    def _stub(*args: Any, **kwargs: Any) -> tuple[list[dict], int]:
        captured.update(kwargs)
        return ([], 0)

    monkeypatch.setattr(routes_assets, "_fetch_asset_list", _stub)
    response = client.get("/assets?risk_band=High")
    assert response.status_code == 200
    assert captured["risk_band"] == "High"


def test_assets_list_rejects_invalid_risk_band() -> None:
    response = client.get("/assets?risk_band=Critical")
    assert response.status_code == 400


def test_assets_list_supports_allowed_sort_by() -> None:
    for field in (
        "asset_id",
        "postcode",
        "industry",
        "asset_value",
        "coverage_limit",
        "risk_score",
        "rainfall_3d_mm",
        "ml_risk_probability",
        "ml_risk_rank",
    ):
        response = client.get(f"/assets?sort_by={field}")
        assert response.status_code == 200, f"sort_by={field}"


def test_assets_list_rejects_invalid_sort_by() -> None:
    response = client.get("/assets?sort_by=evil_column")
    assert response.status_code == 400


def test_assets_list_rejects_invalid_sort_order() -> None:
    response = client.get("/assets?sort_order=sideways")
    assert response.status_code == 400


def test_assets_list_item_schema_matches(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        routes_assets, "_fetch_asset_list", lambda *a, **kw: ([_list_row()], 1)
    )
    payload = client.get("/assets").json()
    item = payload["items"][0]
    for key in (
        "asset_id",
        "business_type",
        "industry",
        "postcode",
        "latitude",
        "longitude",
        "asset_value",
        "annual_revenue",
        "coverage_limit",
        "lga_code",
        "lga_name",
        "risk_score",
        "risk_band",
        "rainfall_3d_mm",
        "station_id",
        "station_distance_km",
        "ml_risk_probability",
        "ml_risk_rank",
    ):
        assert key in item


def test_asset_detail_returns_404_when_missing() -> None:
    response = client.get("/assets/VIC9999")
    assert response.status_code == 404


def test_asset_detail_returns_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(routes_assets, "_fetch_asset_detail", lambda *a, **kw: _detail_row())
    response = client.get("/assets/VIC0001")
    assert response.status_code == 200
    payload = response.json()
    assert payload["asset_id"] == "VIC0001"
    assert payload["top_risk_driver"] == "rainfall_3d_mm"


def test_asset_risk_returns_404_when_asset_missing() -> None:
    response = client.get("/assets/VIC9999/risk")
    assert response.status_code == 404


def test_asset_risk_returns_404_when_risk_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(routes_assets, "_asset_exists", lambda *a, **kw: True)
    response = client.get("/assets/VIC0001/risk")
    assert response.status_code == 404


def test_asset_risk_returns_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(routes_assets, "_asset_exists", lambda *a, **kw: True)
    monkeypatch.setattr(routes_assets, "_fetch_asset_risk", lambda *a, **kw: _risk_row())
    response = client.get("/assets/VIC0001/risk")
    assert response.status_code == 200
    payload = response.json()
    assert payload["risk_band"] == "High"
    assert "raw_score" in payload


def test_asset_rainfall_returns_404_when_asset_missing() -> None:
    response = client.get("/assets/VIC9999/rainfall")
    assert response.status_code == 404


def test_asset_rainfall_returns_404_when_rainfall_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(routes_assets, "_asset_exists", lambda *a, **kw: True)
    response = client.get("/assets/VIC0001/rainfall")
    assert response.status_code == 404


def test_asset_rainfall_returns_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(routes_assets, "_asset_exists", lambda *a, **kw: True)
    monkeypatch.setattr(
        routes_assets, "_fetch_asset_rainfall", lambda *a, **kw: _rainfall_row()
    )
    response = client.get("/assets/VIC0001/rainfall")
    assert response.status_code == 200
    payload = response.json()
    assert payload["rainfall_3d_mm"] == 12.5
    assert payload["extreme_rainfall_flag"] is False


def test_asset_station_returns_404_when_asset_missing() -> None:
    response = client.get("/assets/VIC9999/station")
    assert response.status_code == 404


def test_asset_station_returns_404_when_mapping_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(routes_assets, "_asset_exists", lambda *a, **kw: True)
    response = client.get("/assets/VIC0001/station")
    assert response.status_code == 404


def test_asset_station_returns_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(routes_assets, "_asset_exists", lambda *a, **kw: True)
    monkeypatch.setattr(
        routes_assets, "_fetch_asset_station", lambda *a, **kw: _station_row()
    )
    response = client.get("/assets/VIC0001/station")
    assert response.status_code == 200
    payload = response.json()
    assert payload["station_id"] == "086282"
    assert payload["data_source"] == "bom"


@pytest.mark.parametrize(
    "bare,v1",
    [
        ("/assets", "/api/v1/assets"),
        ("/assets/VIC0001", "/api/v1/assets/VIC0001"),
        ("/assets/VIC0001/risk", "/api/v1/assets/VIC0001/risk"),
        ("/assets/VIC0001/rainfall", "/api/v1/assets/VIC0001/rainfall"),
        ("/assets/VIC0001/station", "/api/v1/assets/VIC0001/station"),
    ],
)
def test_assets_routes_available_under_v1_prefix(bare: str, v1: str) -> None:
    """Each asset path must also be reachable under /api/v1/."""
    bare_status = client.get(bare).status_code
    v1_status = client.get(v1).status_code
    # 200 (list) or 404 (single asset) - both are valid; the important
    # invariant is that the v1 alias is reachable and returns the same
    # same status as the bare path
    assert v1_status == bare_status


def test_routes_do_not_trigger_pipeline_modules(monkeypatch: pytest.MonkeyPatch) -> None:
    """Asset routes must not import or call ingestion/scoring/payout/training/predict."""
    called: list[str] = []

    def _record(name: str) -> Any:
        def _f(*args: Any, **kwargs: Any) -> Any:
            called.append(name)
            raise AssertionError(f"forbidden call to {name} from API")
        return _f

    monkeypatch.setattr("src.ingestion.assets.load_static_assets_to_db", _record("load_assets"))
    monkeypatch.setattr("src.ingestion.rainfall.load_rainfall_stations_to_db", _record("load_stations"))
    monkeypatch.setattr("src.geospatial.station_matching.run_asset_station_matching", _record("match"))
    monkeypatch.setattr("src.geospatial.lga_join.run_asset_lga_assignment", _record("lga"))
    monkeypatch.setattr("src.features.rainfall_features.run_rainfall_feature_generation", _record("features"))
    monkeypatch.setattr("src.risk.scoring.run_asset_risk_scoring", _record("risk"))
    monkeypatch.setattr("src.insurance.payout.run_payout_simulation", _record("payout"))
    monkeypatch.setattr("src.ml.training.run_lightgbm_training", _record("train"))
    monkeypatch.setattr("src.ml.prediction.run_batch_prediction", _record("predict"))

    for path in (
        "/assets",
        "/assets/VIC0001",
        "/assets/VIC0001/risk",
        "/assets/VIC0001/rainfall",
        "/assets/VIC0001/station",
    ):
        client.get(path)
    assert called == [], f"pipelines invoked from API: {called}"
