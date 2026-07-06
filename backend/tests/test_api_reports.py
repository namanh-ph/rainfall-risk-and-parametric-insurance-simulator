"""Tests for the POST /api/v1/reports/export endpoint."""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient

from src.api import routes_reports
from src.main import app

client = TestClient(app)


def _canonical_request() -> dict[str, Any]:
    return {
        "as_of_date": "2025-12-31",
        "simulation_id": "DEFAULT_2025_BASELINE",
        "model_name": "rainfall_risk_lgbm",
        "model_version": "v1",
        "feature_version": "rainfall_risk_features_v1",
        "report_title": "Portfolio Risk Report",
        "include_methodology": True,
        "include_top_assets": True,
        "top_n": 20,
    }


def _stub_export_result() -> dict[str, Any]:
    return {
        "report_id": "portfolio_report_2025-12-31_DEFAULT_2025_BASELINE_rainfall_risk_lgbm_v1",
        "report_title": "Portfolio Risk Report",
        "as_of_date": date(2025, 12, 31),
        "simulation_id": "DEFAULT_2025_BASELINE",
        "model_name": "rainfall_risk_lgbm",
        "model_version": "v1",
        "feature_version": "rainfall_risk_features_v1",
        "output_path": "/tmp/out/portfolio_report.html",
        "relative_output_path": "tmp/out/portfolio_report.html",
        "file_size_bytes": 12345,
        "created_at": datetime(2026, 5, 13, 12, 0, 0, tzinfo=UTC),
        "sections": [
            {
                "section": "portfolio_summary",
                "available": True,
                "row_count": 1,
                "message": None,
            },
            {
                "section": "top_risk_assets",
                "available": True,
                "row_count": 20,
                "message": None,
            },
        ],
        "warnings": [],
    }


def test_post_reports_export_route_exists() -> None:
    routes = {r.path for r in app.routes}
    assert "/api/v1/reports/export" in routes
    # No bare alias for this mutating endpoint
    assert "/reports/export" not in routes


def test_post_reports_export_returns_canonical_shape(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: list[tuple[Any, ...]] = []

    def _fake_export(db: Any, request: Any, **kwargs: Any) -> dict[str, Any]:
        captured.append((db, request, kwargs))
        return _stub_export_result()

    monkeypatch.setattr(routes_reports, "export_portfolio_report", _fake_export)

    response = client.post("/api/v1/reports/export", json=_canonical_request())
    assert response.status_code == 200, response.text
    body = response.json()
    for key in (
        "report_id",
        "report_title",
        "as_of_date",
        "simulation_id",
        "model_name",
        "model_version",
        "feature_version",
        "output_path",
        "relative_output_path",
        "file_size_bytes",
        "created_at",
        "sections",
        "warnings",
    ):
        assert key in body, f"missing {key}"
    assert body["output_path"] == "/tmp/out/portfolio_report.html"
    assert body["file_size_bytes"] == 12345
    assert isinstance(body["sections"], list)
    assert body["sections"][0]["section"] == "portfolio_summary"
    # Service was called with the parsed request body
    assert len(captured) == 1
    _, request_arg, _ = captured[0]
    assert request_arg.simulation_id == "DEFAULT_2025_BASELINE"
    assert request_arg.top_n == 20


def test_post_reports_export_uses_default_request_when_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: list[Any] = []

    def _fake_export(db: Any, request: Any, **kwargs: Any) -> dict[str, Any]:
        captured.append(request)
        return _stub_export_result()

    monkeypatch.setattr(routes_reports, "export_portfolio_report", _fake_export)

    response = client.post("/api/v1/reports/export", json={})
    assert response.status_code == 200, response.text
    assert captured[0].simulation_id == "DEFAULT_2025_BASELINE"
    assert captured[0].top_n == 20


@pytest.mark.parametrize("bad_top_n", [0, -1, 101, 500])
def test_post_reports_export_rejects_invalid_top_n(bad_top_n: int) -> None:
    body = _canonical_request()
    body["top_n"] = bad_top_n
    response = client.post("/api/v1/reports/export", json=body)
    assert response.status_code == 422


@pytest.mark.parametrize(
    "bad_filename",
    [
        "../escape.html",
        "/abs.html",
        "sub/file.html",
        "back\\slash.html",
        "no_extension.txt",
        "weird*name.html",
    ],
)
def test_post_reports_export_rejects_unsafe_output_filename(bad_filename: str) -> None:
    body = _canonical_request()
    body["output_filename"] = bad_filename
    response = client.post("/api/v1/reports/export", json=body)
    assert response.status_code == 422


def test_post_reports_export_rejects_empty_report_title() -> None:
    body = _canonical_request()
    body["report_title"] = ""
    response = client.post("/api/v1/reports/export", json=body)
    assert response.status_code == 422


def test_post_reports_export_propagates_value_error_as_400(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _bad_export(*args: Any, **kwargs: Any) -> dict[str, Any]:
        raise ValueError("missing prerequisite data")

    monkeypatch.setattr(routes_reports, "export_portfolio_report", _bad_export)
    response = client.post("/api/v1/reports/export", json=_canonical_request())
    assert response.status_code == 400
    assert "missing prerequisite" in response.json()["detail"]


def test_post_reports_export_does_not_call_pipeline_services(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    invoked: list[str] = []

    forbidden = [
        ("src.ingestion.assets", "ingest_assets"),
        ("src.ingestion.rainfall", "ingest_rainfall"),
        ("src.ingestion.boundaries", "ingest_boundaries"),
        ("src.geospatial.station_matching", "match_all_assets_to_nearest_stations"),
        ("src.geospatial.lga_join", "assign_assets_to_lgas"),
        ("src.features.rainfall_features", "generate_rainfall_features"),
        ("src.risk.scoring", "score_all_assets"),
        ("src.insurance.payout", "run_payout_simulation"),
        ("src.insurance.simulation", "run_threshold_sensitivity"),
        ("src.insurance.simulation", "run_coverage_multiplier_sensitivity"),
        ("src.insurance.simulation", "run_combined_sensitivity"),
        ("src.ml.dataset", "build_training_data"),
        ("src.ml.training", "train_lightgbm_model"),
        ("src.ml.prediction", "run_batch_prediction"),
    ]

    for module_path, attr in forbidden:
        try:
            module = __import__(module_path, fromlist=[attr])
        except ImportError:
            continue
        if not hasattr(module, attr):
            continue

        def _explode(*args: Any, _name: str = f"{module_path}.{attr}", **kwargs: Any) -> Any:
            invoked.append(_name)
            raise AssertionError(f"Report endpoint must not invoke {_name}")

        monkeypatch.setattr(module, attr, _explode)

    monkeypatch.setattr(
        routes_reports, "export_portfolio_report", lambda *a, **kw: _stub_export_result()
    )
    response = client.post("/api/v1/reports/export", json=_canonical_request())
    assert response.status_code == 200, response.text
    assert invoked == []
