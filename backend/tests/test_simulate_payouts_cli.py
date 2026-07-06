"""Tests for the payout-simulation CLI"""

from __future__ import annotations

from datetime import date
from typing import Any

import pytest

from src.cli.simulate_payouts import _resolve_asset_ids, build_parser, main


def test_parser_help_runs() -> None:
    parser = build_parser()
    with pytest.raises(SystemExit) as exc:
        parser.parse_args(["--help"])
    assert exc.value.code == 0


def test_parser_supports_asset_id_repeated() -> None:
    args = build_parser().parse_args(
        ["--asset-id", "VIC0001", "--asset-id", "VIC0002"]
    )
    assert args.asset_id == ["VIC0001", "VIC0002"]


def test_parser_supports_asset_ids_csv() -> None:
    args = build_parser().parse_args(["--asset-ids", "VIC0001,VIC0002"])
    assert args.asset_ids == "VIC0001,VIC0002"


def test_parser_default_as_of_date_is_2025_12_31() -> None:
    args = build_parser().parse_args([])
    assert args.as_of_date == date(2025, 12, 31)


def test_parser_accepts_custom_as_of_date() -> None:
    args = build_parser().parse_args(["--as-of-date", "2024-06-30"])
    assert args.as_of_date == date(2024, 6, 30)


def test_parser_default_simulation_id_and_name() -> None:
    args = build_parser().parse_args([])
    assert args.simulation_id == "DEFAULT_2025_BASELINE"
    assert "baseline" in args.simulation_name.lower()


def test_parser_accepts_custom_simulation_id() -> None:
    args = build_parser().parse_args(
        ["--simulation-id", "SCENARIO_A", "--simulation-name", "Scenario A"]
    )
    assert args.simulation_id == "SCENARIO_A"
    assert args.simulation_name == "Scenario A"


def test_parser_default_coverage_multiplier_is_1() -> None:
    args = build_parser().parse_args([])
    assert args.coverage_multiplier == 1.0


def test_parser_accepts_custom_coverage_multiplier() -> None:
    args = build_parser().parse_args(["--coverage-multiplier", "1.5"])
    assert args.coverage_multiplier == 1.5


def test_parser_default_replace_existing_true() -> None:
    args = build_parser().parse_args([])
    assert args.replace_existing is True


def test_parser_supports_no_replace_existing() -> None:
    args = build_parser().parse_args(["--no-replace-existing"])
    assert args.replace_existing is False


def test_parser_default_include_risk_band_true() -> None:
    args = build_parser().parse_args([])
    assert args.include_risk_band is True


def test_parser_supports_no_risk_band() -> None:
    args = build_parser().parse_args(["--no-risk-band"])
    assert args.include_risk_band is False


def test_parser_does_not_expose_forbidden_options() -> None:
    parser = build_parser()
    flags = {a.option_strings[0] for a in parser._actions if a.option_strings}
    forbidden = {
        "--n-assets",
        "--generate",
        "--generate-assets",
        "--load-db",
        "--score",
        "--risk",
        "--threshold-sweep",
        "--sensitivity",
        "--train",
        "--predict",
        "--api",
        "--frontend",
        "--report",
    }
    assert flags.isdisjoint(forbidden)


def test_resolve_asset_ids_combines_flags() -> None:
    args = build_parser().parse_args(
        ["--asset-id", "VIC0001", "--asset-ids", "VIC0002,VIC0003"]
    )
    assert _resolve_asset_ids(args) == ["VIC0001", "VIC0002", "VIC0003"]


def test_resolve_asset_ids_returns_none_when_empty() -> None:
    assert _resolve_asset_ids(build_parser().parse_args([])) is None


def test_main_invokes_service_and_prints_summary(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    class _StubSession:
        def close(self) -> None:
            pass

    captured: dict[str, Any] = {}

    def _stub_run(session: Any, **kwargs: Any) -> dict[str, Any]:
        captured.update(kwargs)
        return {
            "simulation_id": "DEFAULT_2025_BASELINE",
            "simulation_name": "Default 2025 baseline parametric payout simulation",
            "as_of_date": date(2025, 12, 31),
            "coverage_multiplier": 1.0,
            "assets_considered": 5000,
            "feature_records_available": 5000,
            "payout_records_generated": 5000,
            "payout_records_inserted": 5000,
            "triggered_assets": 14,
            "not_triggered_assets": 4986,
            "total_coverage_limit": 7_200_000.0,
            "total_estimated_payout": 480_000.0,
            "average_payout_rate": 0.013,
            "replace_existing": True,
        }

    monkeypatch.setattr("src.db.session.SessionLocal", lambda: _StubSession())
    monkeypatch.setattr("src.cli.simulate_payouts.run_payout_simulation", _stub_run)

    rc = main(["--replace-existing"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "simulation=DEFAULT_2025_BASELINE" in out
    assert "considered=5000" in out
    assert "triggered=14" in out
    assert "not_triggered=4986" in out
    assert "total_payout=480000.0" in out
    assert captured["as_of_date"] == date(2025, 12, 31)
    assert captured["simulation_id"] == "DEFAULT_2025_BASELINE"
    assert captured["coverage_multiplier"] == 1.0
    assert captured["replace_existing"] is True
    assert captured["include_risk_band"] is True


def test_main_returns_nonzero_on_value_error(monkeypatch: pytest.MonkeyPatch) -> None:
    class _StubSession:
        def close(self) -> None:
            pass

    monkeypatch.setattr("src.db.session.SessionLocal", lambda: _StubSession())

    def _stub_run_raises(*args: Any, **kwargs: Any) -> dict[str, Any]:
        raise ValueError("No rainfall_features for as_of_date=2025-12-31")

    monkeypatch.setattr(
        "src.cli.simulate_payouts.run_payout_simulation", _stub_run_raises
    )

    rc = main([])
    assert rc == 2
