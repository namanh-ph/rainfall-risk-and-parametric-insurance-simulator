"""Tests for the ingestion CLI argument parser."""

from __future__ import annotations

import pytest

from src.cli.ingest_data import build_parser, main


def test_parser_help_runs() -> None:
    parser = build_parser()
    with pytest.raises(SystemExit) as exc:
        parser.parse_args(["--help"])
    assert exc.value.code == 0


def test_parser_supports_assets_flag() -> None:
    args = build_parser().parse_args(["--assets"])
    assert args.assets is True
    assert args.rainfall is False
    assert args.boundaries is False


def test_parser_supports_rainfall_flag() -> None:
    args = build_parser().parse_args(["--rainfall"])
    assert args.rainfall is True
    assert args.assets is False
    assert args.boundaries is False


def test_parser_supports_boundaries_flag() -> None:
    args = build_parser().parse_args(["--boundaries"])
    assert args.boundaries is True
    assert args.assets is False
    assert args.rainfall is False


def test_parser_supports_replace_existing_flag() -> None:
    args = build_parser().parse_args(["--assets", "--replace-existing"])
    assert args.replace_existing is True


def test_parser_supports_boundary_file_argument() -> None:
    args = build_parser().parse_args(
        ["--boundaries", "--boundary-file", "/tmp/x.geojson"]
    )
    assert str(args.boundary_file).endswith("x.geojson")


def test_parser_does_not_expose_generation_options() -> None:
    parser = build_parser()
    actions = {action.option_strings[0] for action in parser._actions if action.option_strings}
    forbidden = {
        "--n-assets",
        "--generate",
        "--generate-assets",
        "--load-db",
        "--fallback-rainfall",
        "--fallback-boundaries",
        "--seed",
    }
    assert actions.isdisjoint(forbidden), f"forbidden flags exposed: {actions & forbidden}"


def test_parser_accepts_combined_flags() -> None:
    args = build_parser().parse_args(
        [
            "--assets",
            "--rainfall",
            "--boundaries",
            "--replace-existing",
        ]
    )
    assert args.assets is True
    assert args.rainfall is True
    assert args.boundaries is True
    assert args.replace_existing is True


def test_main_returns_nonzero_when_no_flags_specified() -> None:
    rc = main([])
    assert rc != 0
