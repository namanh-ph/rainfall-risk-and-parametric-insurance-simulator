"""Tests for the threshold/coverage-multiplier sensitivity CLI"""

from __future__ import annotations

from datetime import date
from typing import Any

import pytest

from src.cli.run_sensitivity import _resolve_asset_ids, build_parser, main


def test_parser_help_runs() -> None:
    parser = build_parser()
    with pytest.raises(SystemExit) as exc:
        parser.parse_args(["--help"])
    assert exc.value.code == 0


def test_parser_supports_thresholds_flag() -> None:
    args = build_parser().parse_args(["--thresholds"])
    assert args.thresholds is True
    assert args.coverage_multipliers is False
    assert args.combined is False


def test_parser_supports_coverage_multipliers_flag() -> None:
    args = build_parser().parse_args(["--coverage-multipliers"])
    assert args.coverage_multipliers is True


def test_parser_supports_combined_flag() -> None:
    args = build_parser().parse_args(["--combined"])
    assert args.combined is True


def test_parser_supports_asset_id_repeated() -> None:
    args = build_parser().parse_args(
        ["--thresholds", "--asset-id", "VIC0001", "--asset-id", "VIC0002"]
    )
    assert args.asset_id == ["VIC0001", "VIC0002"]


def test_parser_supports_asset_ids_csv() -> None:
    args = build_parser().parse_args(["--thresholds", "--asset-ids", "VIC0001,VIC0002"])
    assert args.asset_ids == "VIC0001,VIC0002"


def test_parser_default_as_of_date_is_2025_12_31() -> None:
    args = build_parser().parse_args(["--thresholds"])
    assert args.as_of_date == date(2025, 12, 31)


def test_parser_accepts_custom_as_of_date() -> None:
    args = build_parser().parse_args(["--thresholds", "--as-of-date", "2024-06-30"])
    assert args.as_of_date == date(2024, 6, 30)


def test_parser_default_replace_existing_true() -> None:
    args = build_parser().parse_args(["--thresholds"])
    assert args.replace_existing is True


def test_parser_supports_no_replace_existing() -> None:
    args = build_parser().parse_args(["--thresholds", "--no-replace-existing"])
    assert args.replace_existing is False


def test_parser_supports_no_risk_band() -> None:
    args = build_parser().parse_args(["--thresholds", "--no-risk-band"])
    assert args.include_risk_band is False


def test_parser_does_not_expose_forbidden_options() -> None:
    parser = build_parser()
    flags = {a.option_strings[0] for a in parser._actions if a.option_strings}
    forbidden = {
        "--n-assets",
        "--generate",
        "--generate-assets",
        "--load-db",
        "--train",
        "--predict",
        "--api",
        "--frontend",
        "--report",
        "--ml",
    }
    assert flags.isdisjoint(forbidden)


def test_resolve_asset_ids_combines_flags() -> None:
    args = build_parser().parse_args(
        ["--thresholds", "--asset-id", "VIC0001", "--asset-ids", "VIC0002,VIC0003"]
    )
    assert _resolve_asset_ids(args) == ["VIC0001", "VIC0002", "VIC0003"]


def test_resolve_asset_ids_returns_none_when_empty() -> None:
    assert _resolve_asset_ids(build_parser().parse_args(["--thresholds"])) is None


def test_main_default_runs_threshold_sensitivity(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    class _StubSession:
        def close(self) -> None:
            pass

    captured: dict[str, Any] = {}

    def _stub_threshold(session: Any, **kwargs: Any) -> dict[str, Any]:
        captured["threshold_called"] = True
        captured.update(kwargs)
        return {
            "as_of_date": date(2025, 12, 31),
            "scenario_count": 2,
            "scenarios": [
                {
                    "simulation_id": "DEFAULT_2025_BASELINE",
                    "simulation_name": "baseline",
                    "threshold_config": [{}],
                    "coverage_multiplier": 1.0,
                    "payout_records_generated": 5000,
                    "payout_records_inserted": 5000,
                    "summary": {
                        "asset_count": 5000,
                        "triggered_assets": 5,
                        "not_triggered_assets": 4995,
                        "trigger_rate": 0.001,
                        "total_coverage_limit": 7_200_000.0,
                        "total_estimated_payout": 25_000.0,
                        "average_payout_rate": 0.0001,
                        "average_estimated_payout": 5.0,
                        "max_estimated_payout": 10_000.0,
                        "payout_rate_distribution": {"0.0": 4995, "0.2": 5},
                    },
                },
            ],
            "replace_existing": True,
        }

    monkeypatch.setattr("src.db.session.SessionLocal", lambda: _StubSession())
    monkeypatch.setattr("src.cli.run_sensitivity.run_threshold_sensitivity", _stub_threshold)

    rc = main([])  # default to --thresholds
    assert rc == 0
    out = capsys.readouterr().out
    assert "scenario=DEFAULT_2025_BASELINE" in out
    assert "triggered=5" in out
    assert captured["threshold_called"] is True


def test_main_combined_runs_both_suites(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    class _StubSession:
        def close(self) -> None:
            pass

    def _stub_combined(session: Any, **kwargs: Any) -> dict[str, Any]:
        return {
            "as_of_date": date(2025, 12, 31),
            "threshold_sensitivity": {
                "as_of_date": date(2025, 12, 31),
                "scenario_count": 1,
                "scenarios": [
                    {
                        "simulation_id": "SWEEP_2025_T060",
                        "coverage_multiplier": 1.0,
                        "payout_records_generated": 1,
                        "payout_records_inserted": 1,
                        "summary": {
                            "triggered_assets": 1,
                            "total_estimated_payout": 1.0,
                            "average_payout_rate": 0.2,
                        },
                    }
                ],
                "replace_existing": True,
            },
            "coverage_multiplier_sensitivity": {
                "as_of_date": date(2025, 12, 31),
                "scenario_count": 1,
                "scenarios": [
                    {
                        "simulation_id": "MULT_2025_X125",
                        "coverage_multiplier": 1.25,
                        "payout_records_generated": 1,
                        "payout_records_inserted": 1,
                        "summary": {
                            "triggered_assets": 0,
                            "total_estimated_payout": 0.0,
                            "average_payout_rate": 0.0,
                        },
                    }
                ],
                "replace_existing": True,
            },
            "replace_existing": True,
        }

    monkeypatch.setattr("src.db.session.SessionLocal", lambda: _StubSession())
    monkeypatch.setattr("src.cli.run_sensitivity.run_combined_sensitivity", _stub_combined)

    rc = main(["--combined"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "Threshold sensitivity" in out
    assert "Coverage-multiplier sensitivity" in out
    assert "scenario=SWEEP_2025_T060" in out
    assert "scenario=MULT_2025_X125" in out


def test_main_returns_nonzero_on_value_error(monkeypatch: pytest.MonkeyPatch) -> None:
    class _StubSession:
        def close(self) -> None:
            pass

    monkeypatch.setattr("src.db.session.SessionLocal", lambda: _StubSession())

    def _stub_raises(*args: Any, **kwargs: Any) -> dict[str, Any]:
        raise ValueError("missing rainfall_features")

    monkeypatch.setattr("src.cli.run_sensitivity.run_threshold_sensitivity", _stub_raises)

    rc = main(["--thresholds"])
    assert rc == 2
