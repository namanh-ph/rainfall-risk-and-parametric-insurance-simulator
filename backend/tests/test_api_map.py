"""Tests for the GeoJSON map endpoints."""

from __future__ import annotations

import json
from typing import Any

import pytest
from fastapi.testclient import TestClient

from src.api import routes_map
from src.main import app

client = TestClient(app)


def _asset_geom_row(asset_id: str = "VIC0001") -> dict[str, Any]:
    return {
        "asset_id": asset_id,
        "business_type": "cafe",
        "industry": "hospitality",
        "postcode": "Richmond",
        "asset_value": 750_000.0,
        "coverage_limit": 80_000.0,
        "lga_code": "LGA20660",
        "lga_name": "Melbourne",
        "risk_score": 42.5,
        "risk_band": "Medium",
        "rainfall_3d_mm": 12.5,
        "trigger_status": "not_triggered",
        "estimated_payout": 0.0,
        "ml_risk_probability": 0.10,
        "ml_risk_rank": 100,
        "top_risk_driver": "rainfall_3d_mm",
        "station_id": "086282",
        "station_distance_km": 4.5,
        "geom_json": json.dumps(
            {"type": "Point", "coordinates": [144.99, -37.82]}
        ),
    }


def _lga_geom_row(lga_code: str = "LGA20660") -> dict[str, Any]:
    return {
        "lga_code": lga_code,
        "lga_name": "Melbourne",
        "state": "VIC",
        "data_source": "abs",
        "asset_count": 250,
        "average_risk_score": 42.0,
        "total_estimated_payout": 0.0,
        "triggered_assets": 0,
        "geom_json": json.dumps(
            {
                "type": "Polygon",
                "coordinates": [
                    [
                        [144.90, -37.85],
                        [145.00, -37.85],
                        [145.00, -37.75],
                        [144.90, -37.75],
                        [144.90, -37.85],
                    ]
                ],
            }
        ),
    }


def _station_geom_row(station_id: str = "086282") -> dict[str, Any]:
    return {
        "station_id": station_id,
        "station_name": "Melbourne Olympic Park",
        "elevation_m": 7.5,
        "data_source": "bom",
        "matched_asset_count": 250,
        "average_station_distance_km": 6.7,
        "geom_json": json.dumps(
            {"type": "Point", "coordinates": [144.98, -37.83]}
        ),
    }


@pytest.fixture(autouse=True)
def _no_real_db(monkeypatch: pytest.MonkeyPatch) -> None:
    """Default to empty result sets unless individual tests override."""
    monkeypatch.setattr(routes_map, "_fetch_map_assets", lambda *a, **kw: [])
    monkeypatch.setattr(routes_map, "_fetch_map_lgas", lambda *a, **kw: [])
    monkeypatch.setattr(routes_map, "_fetch_map_stations", lambda *a, **kw: [])


def test_map_assets_returns_feature_collection() -> None:
    payload = client.get("/map/assets").json()
    assert payload["type"] == "FeatureCollection"
    assert payload["features"] == []


def test_map_assets_features_contain_point_geometries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        routes_map, "_fetch_map_assets", lambda *a, **kw: [_asset_geom_row()]
    )
    payload = client.get("/map/assets").json()
    assert len(payload["features"]) == 1
    feature = payload["features"][0]
    assert feature["type"] == "Feature"
    assert feature["geometry"]["type"] == "Point"
    assert feature["geometry"]["coordinates"] == [144.99, -37.82]
    for key in (
        "asset_id",
        "business_type",
        "industry",
        "risk_score",
        "risk_band",
        "rainfall_3d_mm",
        "trigger_status",
        "estimated_payout",
        "ml_risk_probability",
        "ml_risk_rank",
        "top_risk_driver",
        "station_id",
        "station_distance_km",
    ):
        assert key in feature["properties"]


def test_map_assets_supports_industry_filter(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    def _stub(*args: Any, **kwargs: Any) -> list[dict]:
        captured.update(kwargs)
        return []

    monkeypatch.setattr(routes_map, "_fetch_map_assets", _stub)
    client.get("/map/assets?industry=hospitality")
    assert captured["industry"] == "hospitality"


def test_map_assets_supports_risk_band_filter(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    def _stub(*args: Any, **kwargs: Any) -> list[dict]:
        captured.update(kwargs)
        return []

    monkeypatch.setattr(routes_map, "_fetch_map_assets", _stub)
    response = client.get("/map/assets?risk_band=High")
    assert response.status_code == 200
    assert captured["risk_band"] == "High"


def test_map_assets_rejects_invalid_risk_band() -> None:
    response = client.get("/map/assets?risk_band=Critical")
    assert response.status_code == 400


def test_map_assets_supports_triggered_only(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    def _stub(*args: Any, **kwargs: Any) -> list[dict]:
        captured.update(kwargs)
        return []

    monkeypatch.setattr(routes_map, "_fetch_map_assets", _stub)
    client.get("/map/assets?triggered_only=true")
    assert captured["triggered_only"] is True


def test_map_assets_drops_features_with_malformed_geom(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bad_row = _asset_geom_row()
    bad_row["geom_json"] = "this is not json"
    monkeypatch.setattr(routes_map, "_fetch_map_assets", lambda *a, **kw: [bad_row])
    payload = client.get("/map/assets").json()
    assert payload["features"] == []


def test_map_lgas_returns_feature_collection() -> None:
    payload = client.get("/map/lgas").json()
    assert payload["type"] == "FeatureCollection"
    assert payload["features"] == []


def test_map_lgas_features_contain_polygon_geometries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(routes_map, "_fetch_map_lgas", lambda *a, **kw: [_lga_geom_row()])
    payload = client.get("/map/lgas").json()
    feature = payload["features"][0]
    assert feature["type"] == "Feature"
    assert feature["geometry"]["type"] in ("Polygon", "MultiPolygon")
    for key in (
        "lga_code",
        "lga_name",
        "state",
        "data_source",
        "asset_count",
        "average_risk_score",
        "total_estimated_payout",
        "triggered_assets",
    ):
        assert key in feature["properties"]


def test_map_lgas_supports_include_asset_counts_false(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    def _stub(*args: Any, **kwargs: Any) -> list[dict]:
        captured.update(kwargs)
        return []

    monkeypatch.setattr(routes_map, "_fetch_map_lgas", _stub)
    client.get("/map/lgas?include_asset_counts=false")
    assert captured["include_asset_counts"] is False


def test_map_stations_returns_feature_collection() -> None:
    payload = client.get("/map/stations").json()
    assert payload["type"] == "FeatureCollection"
    assert payload["features"] == []


def test_map_stations_features_contain_point_geometries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        routes_map, "_fetch_map_stations", lambda *a, **kw: [_station_geom_row()]
    )
    payload = client.get("/map/stations").json()
    feature = payload["features"][0]
    assert feature["type"] == "Feature"
    assert feature["geometry"]["type"] == "Point"
    for key in (
        "station_id",
        "station_name",
        "elevation_m",
        "data_source",
        "matched_asset_count",
        "average_station_distance_km",
    ):
        assert key in feature["properties"]


def test_map_stations_supports_include_match_counts_false(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    def _stub(*args: Any, **kwargs: Any) -> list[dict]:
        captured.update(kwargs)
        return []

    monkeypatch.setattr(routes_map, "_fetch_map_stations", _stub)
    client.get("/map/stations?include_match_counts=false")
    assert captured["include_match_counts"] is False


def test_empty_results_return_empty_feature_collection_envelope() -> None:
    for path in ("/map/assets", "/map/lgas", "/map/stations"):
        payload = client.get(path).json()
        assert payload == {"type": "FeatureCollection", "features": []}, path


@pytest.mark.parametrize(
    "path",
    ["/api/v1/map/assets", "/api/v1/map/lgas", "/api/v1/map/stations"],
)
def test_map_routes_available_under_v1_prefix(path: str) -> None:
    response = client.get(path)
    assert response.status_code == 200
    payload = response.json()
    assert payload["type"] == "FeatureCollection"
    assert payload["features"] == []
