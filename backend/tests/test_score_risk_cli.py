"""Tests for the risk-scoring CLI"""

from __future__ import annotations

from datetime import date
from typing import Any

import pytest

from src.cli.score_risk import _resolve_asset_ids, build_parser, main


def test_parser_help_runs() -> None:
    parser = build_parser()
    with pytest.raises(SystemExit) as exc:
        parser.parse_args(["--help"])
    assert exc.value.code == 0


def test_parser_supports_single_asset_id_repeated() -> None:
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


def test_parser_default_replace_existing_true() -> None:
    args = build_parser().parse_args([])
    assert args.replace_existing is True


def test_parser_supports_no_replace_existing() -> None:
    args = build_parser().parse_args(["--no-replace-existing"])
    assert args.replace_existing is False


def test_parser_does_not_expose_forbidden_options() -> None:
    parser = build_parser()
    flags = {a.option_strings[0] for a in parser._actions if a.option_strings}
    forbidden = {
        "--n-assets",
        "--generate",
        "--generate-assets",
        "--load-db",
        "--simulate",
        "--payouts",
        "--train",
        "--predict",
        "--api",
        "--frontend",
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
            "assets_considered": 5000,
            "feature_records_available": 5000,
            "station_mappings_available": 5000,
            "as_of_date": date(2025, 12, 31),
            "risk_score_records_generated": 5000,
            "risk_score_records_inserted": 5000,
            "low_risk_assets": 800,
            "medium_risk_assets": 1900,
            "high_risk_assets": 1800,
            "severe_risk_assets": 500,
            "average_risk_score": 51.7,
            "replace_existing": True,
        }

    monkeypatch.setattr("src.db.session.SessionLocal", lambda: _StubSession())
    monkeypatch.setattr("src.cli.score_risk.run_asset_risk_scoring", _stub_run)

    rc = main(["--replace-existing"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "considered=5000" in out
    assert "low=800" in out
    assert "medium=1900" in out
    assert "high=1800" in out
    assert "severe=500" in out
    assert "avg=51.7" in out
    assert captured["as_of_date"] == date(2025, 12, 31)
    assert captured["replace_existing"] is True
    assert captured["asset_ids"] is None


def test_main_returns_nonzero_on_value_error(monkeypatch: pytest.MonkeyPatch) -> None:
    class _StubSession:
        def close(self) -> None:
            pass

    monkeypatch.setattr("src.db.session.SessionLocal", lambda: _StubSession())

    def _stub_run_raises(*args: Any, **kwargs: Any) -> dict[str, Any]:
        raise ValueError("No rainfall_features for as_of_date=2025-12-31")

    monkeypatch.setattr("src.cli.score_risk.run_asset_risk_scoring", _stub_run_raises)

    rc = main([])
    assert rc == 2
