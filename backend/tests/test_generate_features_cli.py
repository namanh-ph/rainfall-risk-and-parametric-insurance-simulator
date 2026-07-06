"""Tests for the rainfall-feature CLI"""

from __future__ import annotations

from datetime import date
from typing import Any

import pytest

from src.cli.generate_features import _resolve_asset_ids, build_parser, main


def test_parser_help_runs() -> None:
    parser = build_parser()
    with pytest.raises(SystemExit) as exc:
        parser.parse_args(["--help"])
    assert exc.value.code == 0


def test_parser_supports_rainfall_flag() -> None:
    args = build_parser().parse_args(["--rainfall"])
    assert args.rainfall is True


def test_parser_supports_asset_id_repeated() -> None:
    args = build_parser().parse_args(
        ["--rainfall", "--asset-id", "VIC0001", "--asset-id", "VIC0002"]
    )
    assert args.asset_id == ["VIC0001", "VIC0002"]


def test_parser_supports_asset_ids_csv() -> None:
    args = build_parser().parse_args(["--rainfall", "--asset-ids", "VIC0001,VIC0002"])
    assert args.asset_ids == "VIC0001,VIC0002"


def test_parser_default_as_of_date_is_2025_12_31() -> None:
    args = build_parser().parse_args(["--rainfall"])
    assert args.as_of_date == date(2025, 12, 31)


def test_parser_accepts_custom_as_of_date() -> None:
    args = build_parser().parse_args(
        ["--rainfall", "--as-of-date", "2024-06-30"]
    )
    assert args.as_of_date == date(2024, 6, 30)


def test_parser_default_replace_existing_true() -> None:
    args = build_parser().parse_args(["--rainfall"])
    assert args.replace_existing is True


def test_parser_supports_no_replace_existing() -> None:
    args = build_parser().parse_args(["--rainfall", "--no-replace-existing"])
    assert args.replace_existing is False


def test_parser_does_not_expose_generation_or_risk_options() -> None:
    parser = build_parser()
    flags = {a.option_strings[0] for a in parser._actions if a.option_strings}
    forbidden = {
        "--n-assets",
        "--generate",
        "--generate-assets",
        "--load-db",
        "--score",
        "--risk",
        "--simulate",
        "--payouts",
    }
    assert flags.isdisjoint(forbidden)


def test_resolve_asset_ids_combines_flags() -> None:
    args = build_parser().parse_args(
        ["--rainfall", "--asset-id", "VIC0001", "--asset-ids", "VIC0002,VIC0003"]
    )
    assert _resolve_asset_ids(args) == ["VIC0001", "VIC0002", "VIC0003"]


def test_resolve_asset_ids_returns_none_when_empty() -> None:
    args = build_parser().parse_args(["--rainfall"])
    assert _resolve_asset_ids(args) is None


def test_main_returns_nonzero_when_no_feature_family_specified() -> None:
    rc = main([])
    assert rc != 0


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
            "mapped_assets": 5000,
            "stations_used": 15,
            "as_of_date": date(2025, 12, 31),
            "lookback_start_date": date(2025, 1, 1),
            "lookback_end_date": date(2025, 12, 31),
            "feature_records_generated": 5000,
            "feature_records_inserted": 5000,
            "assets_without_station_mapping": 0,
            "assets_without_observations": 0,
            "extreme_rainfall_assets": 125,
            "replace_existing": True,
        }

    monkeypatch.setattr("src.db.session.SessionLocal", lambda: _StubSession())
    monkeypatch.setattr(
        "src.cli.generate_features.run_rainfall_feature_generation", _stub_run
    )

    rc = main(["--rainfall", "--replace-existing"])
    assert rc == 0

    out = capsys.readouterr().out
    assert "considered=5000" in out
    assert "mapped=5000" in out
    assert "stations=15" in out
    assert "generated=5000" in out
    assert "inserted=5000" in out
    assert "extreme=125" in out
    assert captured["as_of_date"] == date(2025, 12, 31)
    assert captured["replace_existing"] is True
    assert captured["asset_ids"] is None


def test_main_returns_nonzero_on_value_error(monkeypatch: pytest.MonkeyPatch) -> None:
    class _StubSession:
        def close(self) -> None:
            pass

    monkeypatch.setattr("src.db.session.SessionLocal", lambda: _StubSession())

    def _stub_run_raises(*args: Any, **kwargs: Any) -> dict[str, Any]:
        raise ValueError("No asset_station_mapping rows")

    monkeypatch.setattr(
        "src.cli.generate_features.run_rainfall_feature_generation", _stub_run_raises
    )

    rc = main(["--rainfall"])
    assert rc == 2
