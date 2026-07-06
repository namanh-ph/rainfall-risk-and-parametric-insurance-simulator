"""Tests for the Jinja2 portfolio_report template."""

from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from src.reports.export import TEMPLATE_DIR, render_report_html


def _minimal_context(
    *,
    include_methodology: bool = True,
    include_top_assets: bool = True,
    warnings: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "report_id": "portfolio_report_2025-12-31_X_Y_Z",
        "report_title": "Portfolio Risk Report",
        "as_of_date": date(2025, 12, 31),
        "simulation_id": "DEFAULT_2025_BASELINE",
        "model_name": "rainfall_risk_lgbm",
        "model_version": "v1",
        "feature_version": "rainfall_risk_features_v1",
        "generated_at": datetime(2026, 5, 13, 12, 0, 0, tzinfo=UTC),
        "include_methodology": include_methodology,
        "include_top_assets": include_top_assets,
        "top_n": 20,
        "portfolio_summary": {
            "total_assets": 5000,
            "total_asset_value": 1_000_000.0,
            "total_coverage_limit": 500_000.0,
            "average_risk_score": 32.5,
            "high_or_severe_assets": 100,
            "triggered_assets": 5,
            "total_estimated_payout": 50_000.0,
            "average_ml_risk_probability": 0.21,
            "risk_band_distribution": [
                {
                    "risk_band": "Low",
                    "asset_count": 2500,
                    "average_risk_score": 12.0,
                    "total_coverage_limit": 100_000.0,
                    "total_estimated_payout": 0.0,
                }
            ],
        },
        "top_risk_assets": [
            {
                "rank": 1,
                "asset_id": "VIC0001",
                "postcode": "Carlton",
                "industry": "hospitality",
                "lga_name": "Melbourne",
                "risk_score": 80.5,
                "risk_band": "Severe",
                "ml_risk_probability": 0.95,
                "ml_risk_rank": 1,
                "top_risk_driver": "rainfall_percentile",
                "rainfall_3d_mm": 45.0,
                "estimated_payout": 0.0,
            }
        ],
        "top_payout_assets": [
            {
                "rank": 1,
                "asset_id": "VIC1234",
                "postcode": "Lakes Entrance",
                "industry": "tourism",
                "lga_name": "East Gippsland",
                "rainfall_3d_mm": 215.0,
                "trigger_status": "triggered",
                "payout_rate": 1.0,
                "coverage_limit": 250_000.0,
                "estimated_payout": 250_000.0,
                "risk_band": "Severe",
            }
        ],
        "risk_by_industry": [
            {
                "industry": "hospitality",
                "asset_count": 100,
                "average_risk_score": 40.0,
                "high_or_severe_assets": 5,
                "triggered_assets": 1,
                "total_coverage_limit": 1_000_000.0,
                "total_estimated_payout": 10_000.0,
            }
        ],
        "risk_by_lga": [
            {
                "lga_code": "LGA20660",
                "lga_name": "Melbourne",
                "asset_count": 100,
                "average_risk_score": 40.0,
                "high_or_severe_assets": 5,
                "triggered_assets": 1,
                "total_coverage_limit": 1_000_000.0,
                "total_estimated_payout": 10_000.0,
            }
        ],
        "model_metadata": {
            "model_name": "rainfall_risk_lgbm",
            "model_version": "v1",
            "feature_version": "rainfall_risk_features_v1",
            "target_name": "target_extreme_rainfall_event",
            "train_row_count": 4000,
            "test_row_count": 1000,
            "feature_count": 38,
            "positive_rate": 0.12,
            "metrics": {"roc_auc": 0.91, "pr_auc": 0.55},
            "mlflow_run_id": "abc123",
            "prediction_count": 5000,
            "artifact_path": "backend/artifacts/models/run",
        },
        "methodology": {
            "title": "Methodology",
            "data_disclaimer": "Data sourced from BoM and ABS.",
            "sections": [
                {"heading": "Asset portfolio", "body": "..."},
                {
                    "heading": "Rainfall and LGA data",
                    "body": (
                        "Rainfall observations from the Bureau of "
                        "Meteorology and LGA polygons from the Australian "
                        "Bureau of Statistics."
                    ),
                },
            ],
        },
        "sections": [
            {
                "section": "portfolio_summary",
                "available": True,
                "row_count": 1,
                "message": None,
            }
        ],
        "warnings": warnings or [],
    }


def test_template_file_exists() -> None:
    assert (TEMPLATE_DIR / "portfolio_report.html.j2").is_file()


def test_template_renders_with_minimal_context() -> None:
    html = render_report_html(_minimal_context())
    assert html.startswith("<!DOCTYPE html>")
    assert "</html>" in html


def test_template_contains_report_title() -> None:
    html = render_report_html(_minimal_context())
    assert "Portfolio Risk Report" in html


def test_template_contains_portfolio_summary_section() -> None:
    html = render_report_html(_minimal_context())
    assert "Portfolio Summary" in html
    assert "Risk band distribution" in html


def test_template_contains_top_risk_assets_when_enabled() -> None:
    html = render_report_html(_minimal_context(include_top_assets=True))
    assert "Top Risk Assets" in html
    assert "VIC0001" in html


def test_template_contains_top_payout_assets_when_enabled() -> None:
    html = render_report_html(_minimal_context(include_top_assets=True))
    assert "Top Payout Assets" in html
    assert "VIC1234" in html


def test_template_omits_top_assets_when_disabled() -> None:
    html = render_report_html(_minimal_context(include_top_assets=False))
    assert "Top Risk Assets" not in html
    assert "Top Payout Assets" not in html


def test_template_contains_methodology_section_when_enabled() -> None:
    html = render_report_html(_minimal_context(include_methodology=True))
    assert "Methodology" in html
    assert "Asset portfolio" in html
    assert "Bureau of Meteorology" in html


def test_template_omits_methodology_section_when_disabled() -> None:
    html = render_report_html(_minimal_context(include_methodology=False))
    assert "Asset portfolio" not in html


def test_template_displays_warnings() -> None:
    html = render_report_html(_minimal_context(warnings=["This is a warning"]))
    assert "Warnings" in html
    assert "This is a warning" in html


def test_template_is_self_contained() -> None:
    html = render_report_html(_minimal_context())
    # No external CSS / JS references
    assert "<script" not in html
    assert "src=" not in html
    assert "href=" not in html
    assert "cdn." not in html
    assert "https://" not in html
    assert "http://" not in html


def test_template_empty_section_shows_human_readable_note() -> None:
    context = _minimal_context()
    context["risk_by_lga"] = []
    html = render_report_html(context)
    assert "No LGA rows available" in html


def test_template_dir_resolves_to_packaged_location() -> None:
    # The template lives inside the installed package, not the repo root
    assert Path(TEMPLATE_DIR).is_dir()
    assert (Path(TEMPLATE_DIR) / "portfolio_report.html.j2").is_file()
