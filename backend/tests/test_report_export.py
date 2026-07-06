"""Unit tests for HTML report data assembly, rendering, and file writing."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

import pytest

from src.reports import export as report_export
from src.reports.export import (
    assemble_report_context,
    build_report_id,
    export_portfolio_report,
    render_report_html,
    resolve_report_output_path,
    write_report_html,
)
from src.schemas.api_reports import ReportExportRequest


def test_build_report_id_is_deterministic_and_safe() -> None:
    rid1 = build_report_id(
        date(2025, 12, 31), "DEFAULT_2025_BASELINE", "rainfall_risk_lgbm", "v1"
    )
    rid2 = build_report_id(
        date(2025, 12, 31), "DEFAULT_2025_BASELINE", "rainfall_risk_lgbm", "v1"
    )
    assert rid1 == rid2
    assert rid1 == (
        "portfolio_report_2025-12-31_DEFAULT_2025_BASELINE_rainfall_risk_lgbm_v1"
    )


def test_build_report_id_sanitizes_unsafe_characters() -> None:
    rid = build_report_id(
        date(2025, 12, 31), "weird/sim id..", "model name", "v1"
    )
    # path separators / dots dropped, single underscores in the middle
    assert "/" not in rid
    assert ".." not in rid
    assert rid.startswith("portfolio_report_2025-12-31_")


def test_resolve_report_output_path_defaults_to_report_id(tmp_path: Path) -> None:
    rid = "portfolio_report_2025-12-31_X_Y_Z"
    path = resolve_report_output_path(None, rid, output_dir=tmp_path)
    assert path.name == f"{rid}.html"
    assert path.parent == tmp_path.resolve()


def test_resolve_report_output_path_accepts_safe_filename(tmp_path: Path) -> None:
    path = resolve_report_output_path("my_report.html", "rid", output_dir=tmp_path)
    assert path.name == "my_report.html"
    assert path.parent == tmp_path.resolve()


@pytest.mark.parametrize(
    "bad",
    [
        "../escape.html",
        "/abs/path.html",
        "sub/dir.html",
        "back\\slash.html",
        "no_extension",
        "no_extension.txt",
        "with space.html",
    ],
)
def test_resolve_report_output_path_rejects_unsafe(bad: str, tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        resolve_report_output_path(bad, "rid", output_dir=tmp_path)


def _empty_summary() -> dict[str, Any]:
    return {
        "total_assets": 0,
        "total_asset_value": 0.0,
        "total_coverage_limit": 0.0,
        "average_risk_score": None,
        "high_or_severe_assets": 0,
        "triggered_assets": 0,
        "total_estimated_payout": 0.0,
        "average_ml_risk_probability": None,
        "risk_band_distribution": [],
    }


def _full_summary() -> dict[str, Any]:
    return {
        "total_assets": 5000,
        "total_asset_value": 1_000_000_000.0,
        "total_coverage_limit": 500_000_000.0,
        "average_risk_score": 32.5,
        "high_or_severe_assets": 410,
        "triggered_assets": 22,
        "total_estimated_payout": 750_000.0,
        "average_ml_risk_probability": 0.18,
        "risk_band_distribution": [
            {
                "risk_band": "Low",
                "asset_count": 2500,
                "average_risk_score": 12.0,
                "total_coverage_limit": 100_000_000.0,
                "total_estimated_payout": 0.0,
            },
        ],
    }


def _top_risk_row() -> dict[str, Any]:
    return {
        "rank": 1,
        "asset_id": "VIC0001",
        "postcode": "Carlton",
        "industry": "hospitality",
        "lga_name": "Melbourne",
        "risk_score": 80.0,
        "risk_band": "Severe",
        "ml_risk_probability": 0.95,
        "ml_risk_rank": 1,
        "top_risk_driver": "rainfall_percentile",
        "rainfall_3d_mm": 45.0,
        "estimated_payout": 0.0,
    }


def _top_payout_row() -> dict[str, Any]:
    return {
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


def _patch_fetchers(
    monkeypatch: pytest.MonkeyPatch,
    *,
    summary: dict[str, Any] | None = None,
    top_risk: list[dict[str, Any]] | None = None,
    top_payout: list[dict[str, Any]] | None = None,
    industry: list[dict[str, Any]] | None = None,
    lga: list[dict[str, Any]] | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, list[Any]]:
    calls: dict[str, list[Any]] = {
        "summary": [],
        "top_risk": [],
        "top_payout": [],
        "industry": [],
        "lga": [],
        "metadata": [],
    }

    def _summary(*args: Any, **kwargs: Any) -> dict[str, Any]:
        calls["summary"].append((args, kwargs))
        return summary if summary is not None else _empty_summary()

    def _top_risk(*args: Any, **kwargs: Any) -> list[dict[str, Any]]:
        calls["top_risk"].append((args, kwargs))
        return top_risk if top_risk is not None else []

    def _top_payout(*args: Any, **kwargs: Any) -> list[dict[str, Any]]:
        calls["top_payout"].append((args, kwargs))
        return top_payout if top_payout is not None else []

    def _industry(*args: Any, **kwargs: Any) -> list[dict[str, Any]]:
        calls["industry"].append((args, kwargs))
        return industry if industry is not None else []

    def _lga(*args: Any, **kwargs: Any) -> list[dict[str, Any]]:
        calls["lga"].append((args, kwargs))
        return lga if lga is not None else []

    def _metadata(*args: Any, **kwargs: Any) -> dict[str, Any]:
        calls["metadata"].append((args, kwargs))
        if metadata is not None:
            return dict(metadata)
        return {
            "model_name": "rainfall_risk_lgbm",
            "model_version": "v1",
            "feature_version": "rainfall_risk_features_v1",
            "target_name": None,
            "train_row_count": None,
            "test_row_count": None,
            "feature_count": None,
            "positive_rate": None,
            "metrics": None,
            "mlflow_run_id": None,
            "prediction_count": 0,
            "artifact_path": "backend/artifacts/models/missing",
            "warnings": ["metadata.json not found at backend/artifacts/models/missing"],
        }

    monkeypatch.setattr(report_export, "fetch_report_portfolio_summary", _summary)
    monkeypatch.setattr(report_export, "fetch_report_top_risk_assets", _top_risk)
    monkeypatch.setattr(report_export, "fetch_report_top_payout_assets", _top_payout)
    monkeypatch.setattr(report_export, "fetch_report_risk_by_industry", _industry)
    monkeypatch.setattr(report_export, "fetch_report_risk_by_lga", _lga)
    monkeypatch.setattr(report_export, "fetch_report_model_metadata", _metadata)
    return calls


REQUIRED_CONTEXT_KEYS = {
    "report_id",
    "report_title",
    "as_of_date",
    "simulation_id",
    "model_name",
    "model_version",
    "feature_version",
    "generated_at",
    "portfolio_summary",
    "top_risk_assets",
    "top_payout_assets",
    "risk_by_industry",
    "risk_by_lga",
    "model_metadata",
    "methodology",
    "sections",
    "warnings",
}


def test_assemble_report_context_returns_all_required_keys(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_fetchers(monkeypatch, summary=_full_summary())
    request = ReportExportRequest()
    context = assemble_report_context(db=object(), request=request)
    assert REQUIRED_CONTEXT_KEYS.issubset(context.keys())


def test_assemble_report_context_records_warnings_for_empty_sections(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_fetchers(monkeypatch, summary=_empty_summary())
    request = ReportExportRequest()
    context = assemble_report_context(db=object(), request=request)

    # Empty summary -> warning about zero assets
    warning_text = " ".join(context["warnings"])
    assert "zero assets" in warning_text or "Portfolio summary" in warning_text
    # Top risk/payout/lga sections are all empty -> warnings recorded
    section_names = {s["section"] for s in context["sections"]}
    assert {
        "portfolio_summary",
        "top_risk_assets",
        "top_payout_assets",
        "risk_by_industry",
        "risk_by_lga",
        "model_metadata",
    } <= section_names


def test_assemble_report_context_skips_top_assets_when_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = _patch_fetchers(monkeypatch, summary=_full_summary())
    request = ReportExportRequest(include_top_assets=False)
    context = assemble_report_context(db=object(), request=request)
    assert context["top_risk_assets"] == []
    assert context["top_payout_assets"] == []
    assert calls["top_risk"] == []
    assert calls["top_payout"] == []


def test_render_report_html_returns_string_with_title(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_fetchers(
        monkeypatch,
        summary=_full_summary(),
        top_risk=[_top_risk_row()],
        top_payout=[_top_payout_row()],
        industry=[
            {
                "industry": "hospitality",
                "asset_count": 100,
                "average_risk_score": 40.0,
                "high_or_severe_assets": 5,
                "triggered_assets": 1,
                "total_coverage_limit": 1_000_000.0,
                "total_estimated_payout": 100_000.0,
            }
        ],
        lga=[
            {
                "lga_code": "LGA20660",
                "lga_name": "Melbourne",
                "asset_count": 100,
                "average_risk_score": 40.0,
                "high_or_severe_assets": 5,
                "triggered_assets": 1,
                "total_coverage_limit": 1_000_000.0,
                "total_estimated_payout": 100_000.0,
            }
        ],
    )
    request = ReportExportRequest()
    context = assemble_report_context(db=object(), request=request)
    html = render_report_html(context)
    assert isinstance(html, str)
    assert "Portfolio Risk Report" in html
    assert "Portfolio Summary" in html


def test_write_report_html_creates_parent_directories_and_utf8(tmp_path: Path) -> None:
    target = tmp_path / "subdir" / "report.html"
    written = write_report_html("<html>cafÃ©</html>", target)
    assert written.is_file()
    assert written.read_text(encoding="utf-8") == "<html>cafÃ©</html>"


def test_export_portfolio_report_returns_canonical_response_fields(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _patch_fetchers(monkeypatch, summary=_full_summary())
    request = ReportExportRequest()
    result = export_portfolio_report(db=object(), request=request, output_dir=tmp_path)
    expected_keys = {
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
    }
    assert expected_keys.issubset(result.keys())
    assert Path(result["output_path"]).is_file()
    assert result["file_size_bytes"] > 0
    assert result["report_title"] == "Portfolio Risk Report"


def test_export_portfolio_report_does_not_invoke_pipeline_jobs(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Smoke-test that no upstream pipeline import is exercised by the exporter."""
    forbidden_attrs = [
        ("src.ingestion.assets", "ingest_assets"),
        ("src.ingestion.rainfall", "ingest_rainfall"),
        ("src.ingestion.boundaries", "ingest_boundaries"),
        ("src.geospatial.station_matching", "match_all_assets_to_nearest_stations"),
        ("src.geospatial.lga_join", "assign_assets_to_lgas"),
        ("src.features.rainfall_features", "generate_rainfall_features"),
        ("src.risk.scoring", "score_all_assets"),
        ("src.insurance.payout", "run_payout_simulation"),
        ("src.insurance.simulation", "run_threshold_sensitivity"),
        ("src.ml.dataset", "build_training_data"),
        ("src.ml.training", "train_lightgbm_model"),
        ("src.ml.prediction", "run_batch_prediction"),
    ]
    invoked: list[str] = []
    for module_path, attr in forbidden_attrs:
        try:
            module = __import__(module_path, fromlist=[attr])
        except ImportError:
            continue
        if not hasattr(module, attr):
            continue

        def _explode(*args: Any, _name: str = f"{module_path}.{attr}", **kwargs: Any) -> Any:
            invoked.append(_name)
            raise AssertionError(f"Report export must not invoke {_name}")

        monkeypatch.setattr(module, attr, _explode)

    _patch_fetchers(monkeypatch, summary=_full_summary())
    request = ReportExportRequest()
    result = export_portfolio_report(db=object(), request=request, output_dir=tmp_path)
    assert invoked == []
    assert Path(result["output_path"]).is_file()


def test_export_portfolio_report_overwrites_existing_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _patch_fetchers(monkeypatch, summary=_full_summary())
    request = ReportExportRequest()
    first = export_portfolio_report(db=object(), request=request, output_dir=tmp_path)
    second = export_portfolio_report(db=object(), request=request, output_dir=tmp_path)
    assert first["output_path"] == second["output_path"]
    # File still exists and has non-zero size after the second run
    assert Path(second["output_path"]).is_file()
    assert second["file_size_bytes"] > 0


class _FakeRow:
    def __init__(self, mapping: dict[str, Any]) -> None:
        self._mapping = mapping


class _FakeResult:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = [_FakeRow(r) for r in rows]

    def __iter__(self):
        return iter(self._rows)

    def first(self) -> _FakeRow | None:
        return self._rows[0] if self._rows else None

    def scalar(self) -> Any:
        if not self._rows:
            return 0
        first = self._rows[0]._mapping
        return next(iter(first.values()))


class _FakeSession:
    def __init__(self, results: list[list[dict[str, Any]]]) -> None:
        self._results = list(results)

    def execute(self, *args: Any, **kwargs: Any) -> _FakeResult:
        if not self._results:
            return _FakeResult([])
        return _FakeResult(self._results.pop(0))


def test_fetch_report_portfolio_summary_with_mocked_session() -> None:
    totals = [
        {
            "total_assets": 1,
            "total_asset_value": 100.0,
            "total_coverage_limit": 50.0,
            "average_risk_score": 25.0,
            "high_or_severe_assets": 0,
            "triggered_assets": 0,
            "total_estimated_payout": 0.0,
            "average_ml_risk_probability": 0.1,
        }
    ]
    bands = [
        {
            "risk_band": "Low",
            "asset_count": 1,
            "average_risk_score": 25.0,
            "total_coverage_limit": 50.0,
            "total_estimated_payout": 0.0,
        }
    ]
    session = _FakeSession([totals, bands])
    summary = report_export.fetch_report_portfolio_summary(
        session,  # type: ignore[arg-type]
        as_of_date=date(2025, 12, 31),
        simulation_id="DEFAULT_2025_BASELINE",
        model_name="rainfall_risk_lgbm",
        model_version="v1",
    )
    assert summary["total_assets"] == 1
    assert summary["risk_band_distribution"][0]["risk_band"] == "Low"
