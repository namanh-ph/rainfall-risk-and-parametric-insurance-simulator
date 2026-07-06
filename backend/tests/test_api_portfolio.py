"""Tests for the portfolio summary and risk-ranking endpoints"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from src.api import routes_portfolio
from src.main import app

client = TestClient(app)


def _band(name: str, **overrides: Any) -> dict[str, Any]:
    base = {
        "risk_band": name,
        "asset_count": 100,
        "average_risk_score": 42.0,
        "total_coverage_limit": 1_000_000.0,
        "total_estimated_payout": 0.0,
    }
    base.update(overrides)
    return base


def _industry(industry: str = "hospitality", **overrides: Any) -> dict[str, Any]:
    base = {
        "industry": industry,
        "asset_count": 50,
        "average_risk_score": 40.0,
        "high_or_severe_assets": 5,
        "triggered_assets": 1,
        "total_coverage_limit": 500_000.0,
        "total_estimated_payout": 10_000.0,
    }
    base.update(overrides)
    return base


def _lga(code: str = "LGA20660", **overrides: Any) -> dict[str, Any]:
    base = {
        "lga_code": code,
        "lga_name": "Melbourne",
        "asset_count": 30,
        "average_risk_score": 45.0,
        "high_or_severe_assets": 3,
        "triggered_assets": 0,
        "total_coverage_limit": 250_000.0,
        "total_estimated_payout": 0.0,
    }
    base.update(overrides)
    return base


def _ranking_row(asset_id: str = "VIC0001", **overrides: Any) -> dict[str, Any]:
    base = {
        "asset_id": asset_id,
        "business_type": "warehouse",
        "industry": "logistics",
        "postcode": "Dandenong",
        "lga_code": "LGA21890c",
        "lga_name": "Greater Dandenong",
        "asset_value": 1_500_000.0,
        "coverage_limit": 250_000.0,
        "risk_score": 80.5,
        "risk_band": "Severe",
        "rainfall_3d_mm": 25.5,
        "rainfall_percentile": 0.94,
        "extreme_rainfall_flag": False,
        "trigger_status": "not_triggered",
        "estimated_payout": 0.0,
        "ml_risk_probability": 0.81,
        "ml_risk_rank": 1,
        "top_risk_driver": "rainfall_percentile",
    }
    base.update(overrides)
    return base


@pytest.fixture(autouse=True)
def _no_real_db(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        routes_portfolio,
        "_fetch_portfolio_totals",
        lambda *a, **kw: {
            "total_assets": 0,
            "total_asset_value": 0,
            "total_coverage_limit": 0,
            "average_risk_score": None,
            "high_or_severe_assets": 0,
            "triggered_assets": 0,
            "total_estimated_payout": 0,
            "average_ml_risk_probability": None,
        },
    )
    monkeypatch.setattr(routes_portfolio, "_fetch_risk_band_distribution", lambda *a, **kw: [])
    monkeypatch.setattr(routes_portfolio, "_fetch_industry_summary", lambda *a, **kw: [])
    monkeypatch.setattr(routes_portfolio, "_fetch_lga_summary", lambda *a, **kw: [])
    monkeypatch.setattr(routes_portfolio, "_fetch_risk_ranking", lambda *a, **kw: ([], 0))


def test_portfolio_summary_route_exists() -> None:
    response = client.get("/api/v1/portfolio/summary")
    assert response.status_code == 200


def test_portfolio_summary_returns_canonical_keys() -> None:
    payload = client.get("/api/v1/portfolio/summary").json()
    for key in (
        "as_of_date",
        "simulation_id",
        "model_name",
        "model_version",
        "total_assets",
        "total_asset_value",
        "total_coverage_limit",
        "average_risk_score",
        "high_or_severe_assets",
        "triggered_assets",
        "total_estimated_payout",
        "average_ml_risk_probability",
        "risk_band_distribution",
        "industry_summary",
        "lga_summary",
    ):
        assert key in payload


def test_portfolio_summary_with_full_data(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        routes_portfolio,
        "_fetch_portfolio_totals",
        lambda *a, **kw: {
            "total_assets": 5000,
            "total_asset_value": 8_000_000_000.0,
            "total_coverage_limit": 1_500_000_000.0,
            "average_risk_score": 45.6,
            "high_or_severe_assets": 800,
            "triggered_assets": 25,
            "total_estimated_payout": 1_250_000.0,
            "average_ml_risk_probability": 0.18,
        },
    )
    monkeypatch.setattr(
        routes_portfolio,
        "_fetch_risk_band_distribution",
        lambda *a, **kw: [_band("Low"), _band("Medium"), _band("High"), _band("Severe")],
    )
    monkeypatch.setattr(
        routes_portfolio, "_fetch_industry_summary", lambda *a, **kw: [_industry()]
    )
    monkeypatch.setattr(routes_portfolio, "_fetch_lga_summary", lambda *a, **kw: [_lga()])

    payload = client.get("/api/v1/portfolio/summary").json()
    assert payload["total_assets"] == 5000
    assert payload["triggered_assets"] == 25
    assert len(payload["risk_band_distribution"]) == 4
    assert payload["risk_band_distribution"][0]["risk_band"] == "Low"
    assert payload["industry_summary"][0]["industry"] == "hospitality"
    assert payload["lga_summary"][0]["lga_code"] == "LGA20660"


def test_portfolio_summary_tolerates_missing_payout_or_ml_rows() -> None:
    # default fixture returns no rows / no totals; endpoint must still 200
    response = client.get("/api/v1/portfolio/summary")
    assert response.status_code == 200
    payload = response.json()
    assert payload["total_assets"] == 0
    assert payload["average_risk_score"] is None
    assert payload["average_ml_risk_probability"] is None


def test_risk_ranking_route_exists() -> None:
    response = client.get("/api/v1/portfolio/risk-ranking")
    assert response.status_code == 200


def test_risk_ranking_returns_pagination_metadata(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        routes_portfolio,
        "_fetch_risk_ranking",
        lambda *a, **kw: ([_ranking_row("VIC0001"), _ranking_row("VIC0002")], 2),
    )
    payload = client.get("/api/v1/portfolio/risk-ranking?limit=10&offset=0").json()
    assert payload["pagination"] == {"limit": 10, "offset": 0, "total": 2, "returned": 2}
    assert payload["items"][0]["rank"] == 1
    assert payload["items"][1]["rank"] == 2


def test_risk_ranking_supports_risk_band_filter(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    def _stub(*args: Any, **kwargs: Any) -> tuple[list[dict], int]:
        captured.update(kwargs)
        return ([], 0)

    monkeypatch.setattr(routes_portfolio, "_fetch_risk_ranking", _stub)
    response = client.get("/api/v1/portfolio/risk-ranking?risk_band=Severe")
    assert response.status_code == 200
    assert captured["risk_band"] == "Severe"


def test_risk_ranking_rejects_invalid_risk_band() -> None:
    response = client.get("/api/v1/portfolio/risk-ranking?risk_band=Critical")
    assert response.status_code == 400


def test_risk_ranking_supports_allowed_sort_by() -> None:
    for field in (
        "risk_score",
        "ml_risk_probability",
        "estimated_payout",
        "rainfall_3d_mm",
        "asset_value",
        "coverage_limit",
        "ml_risk_rank",
    ):
        response = client.get(f"/api/v1/portfolio/risk-ranking?sort_by={field}")
        assert response.status_code == 200, f"sort_by={field}"


def test_risk_ranking_rejects_invalid_sort_by() -> None:
    response = client.get("/api/v1/portfolio/risk-ranking?sort_by=evil_column")
    assert response.status_code == 400


def test_risk_ranking_rejects_invalid_sort_order() -> None:
    response = client.get("/api/v1/portfolio/risk-ranking?sort_order=sideways")
    assert response.status_code == 400


def test_risk_ranking_supports_triggered_only(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    def _stub(*args: Any, **kwargs: Any) -> tuple[list[dict], int]:
        captured.update(kwargs)
        return ([], 0)

    monkeypatch.setattr(routes_portfolio, "_fetch_risk_ranking", _stub)
    client.get("/api/v1/portfolio/risk-ranking?triggered_only=true")
    assert captured["triggered_only"] is True


def test_risk_ranking_rank_reflects_sorted_offset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        routes_portfolio,
        "_fetch_risk_ranking",
        lambda *a, **kw: ([_ranking_row("VIC0050"), _ranking_row("VIC0051")], 1000),
    )
    payload = client.get(
        "/api/v1/portfolio/risk-ranking?limit=2&offset=49"
    ).json()
    assert payload["items"][0]["rank"] == 50
    assert payload["items"][1]["rank"] == 51
    assert payload["pagination"]["total"] == 1000
