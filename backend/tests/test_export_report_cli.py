"""Tests for the export_report CLI."""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any

import pytest

from src.cli import export_report as cli


def _stub_result() -> dict[str, Any]:
    return {
        "report_id": "portfolio_report_2025-12-31_DEFAULT_2025_BASELINE_rainfall_risk_lgbm_v1",
        "report_title": "Portfolio Risk Report",
        "as_of_date": date(2025, 12, 31),
        "simulation_id": "DEFAULT_2025_BASELINE",
        "model_name": "rainfall_risk_lgbm",
        "model_version": "v1",
        "feature_version": "rainfall_risk_features_v1",
        "output_path": "/tmp/out/portfolio.html",
        "relative_output_path": "tmp/out/portfolio.html",
        "file_size_bytes": 1024,
        "created_at": datetime(2026, 5, 13, 12, 0, 0, tzinfo=UTC),
        "sections": [
            {
                "section": "portfolio_summary",
                "available": True,
                "row_count": 1,
                "message": None,
            }
        ],
        "warnings": [],
    }


def test_cli_help_runs(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc_info:
        cli.main(["--help"])
    assert exc_info.value.code == 0
    captured = capsys.readouterr()
    assert "export_report" in captured.out


@pytest.mark.parametrize(
    "flag",
    [
        "--as-of-date",
        "--simulation-id",
        "--model-name",
        "--model-version",
        "--feature-version",
        "--report-title",
        "--output",
        "--top-n",
        "--no-methodology",
        "--no-top-assets",
    ],
)
def test_cli_supports_documented_flag(flag: str) -> None:
    parser = cli.build_parser()
    help_text = parser.format_help()
    assert flag in help_text


def test_cli_does_not_expose_disallowed_options() -> None:
    parser = cli.build_parser()
    help_text = parser.format_help()
    for forbidden in (
        # Asset generation
        "--generate-assets",
        # Ingestion
        "--ingest",
        "--ingest-assets",
        "--ingest-rainfall",
        "--ingest-boundaries",
        "--fallback-rainfall",
        "--fallback-boundaries",
        # Geospatial
        "--match-stations",
        "--assign-lgas",
        # Feature engineering
        "--generate-features",
        "--rainfall-features",
        # Risk scoring
        "--score-risk",
        # Payout simulation / sensitivity
        "--simulate-payouts",
        "--threshold-sensitivity",
        "--coverage-multiplier-sensitivity",
        # ML
        "--build-training-data",
        "--train-model",
        "--predict-model",
        # API / frontend / charts
        "--serve",
        "--frontend",
        "--charts",
        "--pdf",
    ):
        assert forbidden not in help_text, f"CLI must not expose {forbidden}"


def test_cli_invokes_export_service_with_mocked_session(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    captured: list[tuple[Any, Any]] = []

    class _Sess:
        def close(self) -> None:
            pass

    # Replace the SessionLocal import inside main()
    import src.db.session as session_module

    monkeypatch.setattr(session_module, "SessionLocal", lambda: _Sess())

    def _fake_export(db: Any, request: Any, **kwargs: Any) -> dict[str, Any]:
        captured.append((db, request))
        return _stub_result()

    monkeypatch.setattr(cli, "export_portfolio_report", _fake_export)

    code = cli.main(
        [
            "--as-of-date",
            "2025-12-31",
            "--simulation-id",
            "DEFAULT_2025_BASELINE",
            "--model-name",
            "rainfall_risk_lgbm",
            "--model-version",
            "v1",
            "--feature-version",
            "rainfall_risk_features_v1",
            "--top-n",
            "10",
        ]
    )
    assert code == 0
    assert len(captured) == 1
    _, request = captured[0]
    assert request.simulation_id == "DEFAULT_2025_BASELINE"
    assert request.top_n == 10
    out = capsys.readouterr().out
    assert "report_id=" in out
    assert "output=" in out
    assert "size_bytes=1024" in out


def test_cli_returns_nonzero_on_validation_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _Sess:
        def close(self) -> None:
            pass

    import src.db.session as session_module

    monkeypatch.setattr(session_module, "SessionLocal", lambda: _Sess())

    def _bad_export(*args: Any, **kwargs: Any) -> dict[str, Any]:
        raise ValueError("missing prerequisites")

    monkeypatch.setattr(cli, "export_portfolio_report", _bad_export)

    code = cli.main(
        [
            "--as-of-date",
            "2025-12-31",
            "--simulation-id",
            "DEFAULT_2025_BASELINE",
            "--model-name",
            "rainfall_risk_lgbm",
            "--model-version",
            "v1",
        ]
    )
    assert code == 2


def test_cli_no_methodology_flag_disables_methodology(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: list[Any] = []

    class _Sess:
        def close(self) -> None:
            pass

    import src.db.session as session_module

    monkeypatch.setattr(session_module, "SessionLocal", lambda: _Sess())

    def _fake_export(db: Any, request: Any, **kwargs: Any) -> dict[str, Any]:
        captured.append(request)
        return _stub_result()

    monkeypatch.setattr(cli, "export_portfolio_report", _fake_export)

    code = cli.main(["--no-methodology", "--no-top-assets"])
    assert code == 0
    assert captured[0].include_methodology is False
    assert captured[0].include_top_assets is False
