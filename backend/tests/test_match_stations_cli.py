"""Tests for the asset-to-station matching CLI"""

from __future__ import annotations

from typing import Any

import pytest

from src.cli.match_stations import _resolve_asset_ids, build_parser, main


def test_parser_help_runs() -> None:
    parser = build_parser()
    with pytest.raises(SystemExit) as exc:
        parser.parse_args(["--help"])
    assert exc.value.code == 0


def test_parser_supports_single_asset_id_repeated() -> None:
    args = build_parser().parse_args(["--asset-id", "VIC0001", "--asset-id", "VIC0002"])
    assert args.asset_id == ["VIC0001", "VIC0002"]


def test_parser_supports_asset_ids_csv() -> None:
    args = build_parser().parse_args(["--asset-ids", "VIC0001,VIC0002,VIC0003"])
    assert args.asset_ids == "VIC0001,VIC0002,VIC0003"


def test_parser_supports_max_distance_km() -> None:
    args = build_parser().parse_args(["--max-distance-km", "75"])
    assert args.max_distance_km == 75.0


def test_parser_supports_replace_existing_default() -> None:
    args = build_parser().parse_args([])
    assert args.replace_existing is True


def test_parser_supports_no_replace_existing_flag() -> None:
    args = build_parser().parse_args(["--no-replace-existing"])
    assert args.replace_existing is False


def test_parser_does_not_expose_generation_options() -> None:
    parser = build_parser()
    flags = {a.option_strings[0] for a in parser._actions if a.option_strings}
    forbidden = {"--n-assets", "--generate", "--generate-assets", "--load-db"}
    assert flags.isdisjoint(forbidden)


def test_resolve_asset_ids_combines_single_and_csv_flags() -> None:
    args = build_parser().parse_args(
        ["--asset-id", "VIC0001", "--asset-ids", "VIC0002,VIC0003"]
    )
    assert _resolve_asset_ids(args) == ["VIC0001", "VIC0002", "VIC0003"]


def test_resolve_asset_ids_returns_none_when_no_filters() -> None:
    args = build_parser().parse_args([])
    assert _resolve_asset_ids(args) is None


def test_resolve_asset_ids_strips_whitespace_in_csv() -> None:
    args = build_parser().parse_args(["--asset-ids", " VIC0001 , VIC0002 "])
    assert _resolve_asset_ids(args) == ["VIC0001", "VIC0002"]


def test_main_invokes_matching_service_and_prints_summary(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Stub `run_asset_station_matching` and verify CLI plumbing"""

    class _StubSession:
        def close(self) -> None:
            pass

    def _stub_session_local() -> _StubSession:
        return _StubSession()

    captured: dict[str, Any] = {}

    def _stub_run(session: Any, **kwargs: Any) -> dict[str, Any]:
        captured["session"] = session
        captured.update(kwargs)
        return {
            "assets_considered": 5000,
            "stations_available": 15,
            "matches_generated": 5000,
            "mappings_inserted": 5000,
            "unmatched_assets": 0,
            "max_distance_km": None,
            "replace_existing": True,
        }

    monkeypatch.setattr("src.db.session.SessionLocal", _stub_session_local)
    monkeypatch.setattr(
        "src.cli.match_stations.run_asset_station_matching", _stub_run
    )

    rc = main(["--replace-existing"])
    assert rc == 0

    out = capsys.readouterr().out
    assert "considered=5000" in out
    assert "stations=15" in out
    assert "matched=5000" in out
    assert "inserted=5000" in out
    assert "unmatched=0" in out

    assert captured["asset_ids"] is None
    assert captured["max_distance_km"] is None
    assert captured["replace_existing"] is True


def test_main_returns_nonzero_on_value_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _StubSession:
        def close(self) -> None:
            pass

    monkeypatch.setattr("src.db.session.SessionLocal", lambda: _StubSession())

    def _stub_run_raises(*args: Any, **kwargs: Any) -> dict[str, Any]:
        raise ValueError("No assets in database")

    monkeypatch.setattr(
        "src.cli.match_stations.run_asset_station_matching", _stub_run_raises
    )
    rc = main([])
    assert rc == 2
