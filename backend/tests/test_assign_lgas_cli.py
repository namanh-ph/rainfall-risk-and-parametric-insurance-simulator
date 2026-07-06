"""Tests for the asset-to-LGA assignment CLI"""

from __future__ import annotations

from typing import Any

import pytest

from src.cli.assign_lgas import _resolve_asset_ids, build_parser, main


def test_parser_help_runs() -> None:
    parser = build_parser()
    with pytest.raises(SystemExit) as exc:
        parser.parse_args(["--help"])
    assert exc.value.code == 0


def test_parser_supports_single_asset_id_repeated() -> None:
    args = build_parser().parse_args(["--asset-id", "VIC0001", "--asset-id", "VIC0002"])
    assert args.asset_id == ["VIC0001", "VIC0002"]


def test_parser_supports_asset_ids_csv() -> None:
    args = build_parser().parse_args(["--asset-ids", "VIC0001,VIC0002"])
    assert args.asset_ids == "VIC0001,VIC0002"


def test_parser_default_allow_nearest_fallback_true() -> None:
    args = build_parser().parse_args([])
    assert args.allow_nearest_fallback is True


def test_parser_supports_no_nearest_fallback_flag() -> None:
    args = build_parser().parse_args(["--no-nearest-fallback"])
    assert args.allow_nearest_fallback is False


def test_parser_supports_allow_nearest_fallback_flag() -> None:
    args = build_parser().parse_args(["--allow-nearest-fallback"])
    assert args.allow_nearest_fallback is True


def test_parser_default_max_fallback_distance_is_25() -> None:
    args = build_parser().parse_args([])
    assert args.max_fallback_distance_km == 25.0


def test_parser_accepts_custom_max_fallback_distance() -> None:
    args = build_parser().parse_args(["--max-fallback-distance-km", "50"])
    assert args.max_fallback_distance_km == 50.0


def test_parser_accepts_none_for_max_fallback_distance() -> None:
    args = build_parser().parse_args(["--max-fallback-distance-km", "none"])
    assert args.max_fallback_distance_km is None


def test_parser_default_replace_existing_true() -> None:
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


def test_main_invokes_assignment_service_and_prints_summary(
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
            "lga_boundaries_available": 48,
            "assignments_generated": 5000,
            "assets_updated": 4900,
            "unmatched_assets": 100,
            "covers_assignments": 4700,
            "intersects_assignments": 0,
            "nearest_fallback_assignments": 200,
            "allow_nearest_fallback": True,
            "max_fallback_distance_km": 25.0,
            "replace_existing": True,
        }

    monkeypatch.setattr("src.db.session.SessionLocal", lambda: _StubSession())
    monkeypatch.setattr("src.cli.assign_lgas.run_asset_lga_assignment", _stub_run)

    rc = main(["--replace-existing"])
    assert rc == 0

    out = capsys.readouterr().out
    assert "considered=5000" in out
    assert "lgas=48" in out
    assert "updated=4900" in out
    assert "covers=4700" in out
    assert "fallback=200" in out
    assert "unmatched=100" in out

    assert captured["asset_ids"] is None
    assert captured["allow_nearest_fallback"] is True
    assert captured["max_fallback_distance_km"] == 25.0
    assert captured["replace_existing"] is True


def test_main_returns_nonzero_on_value_error(monkeypatch: pytest.MonkeyPatch) -> None:
    class _StubSession:
        def close(self) -> None:
            pass

    monkeypatch.setattr("src.db.session.SessionLocal", lambda: _StubSession())

    def _stub_run_raises(*args: Any, **kwargs: Any) -> dict[str, Any]:
        raise ValueError("No lga_boundaries in database")

    monkeypatch.setattr(
        "src.cli.assign_lgas.run_asset_lga_assignment", _stub_run_raises
    )

    rc = main([])
    assert rc == 2
