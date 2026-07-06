"""Tests for the training-data CLI"""

from __future__ import annotations

from datetime import date
from typing import Any

import pytest

from src.cli.build_training_data import _resolve_asset_ids, build_parser, main


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


def test_parser_default_feature_version() -> None:
    args = build_parser().parse_args([])
    assert args.feature_version == "rainfall_risk_features_v1"


def test_parser_accepts_custom_feature_version() -> None:
    args = build_parser().parse_args(["--feature-version", "experimental_v2"])
    assert args.feature_version == "experimental_v2"


def test_parser_default_baseline_simulation_id() -> None:
    args = build_parser().parse_args([])
    assert args.baseline_simulation_id == "DEFAULT_2025_BASELINE"


def test_parser_supports_no_replace_existing() -> None:
    args = build_parser().parse_args(["--no-replace-existing"])
    assert args.replace_existing is False


def test_parser_default_test_size_and_seed() -> None:
    args = build_parser().parse_args([])
    assert args.test_size == 0.2
    assert args.split_seed == 42


def test_parser_accepts_custom_test_size_and_seed() -> None:
    args = build_parser().parse_args(["--test-size", "0.3", "--split-seed", "7"])
    assert args.test_size == 0.3
    assert args.split_seed == 7


def test_parser_does_not_expose_forbidden_options() -> None:
    parser = build_parser()
    flags = {a.option_strings[0] for a in parser._actions if a.option_strings}
    forbidden = {
        "--n-assets",
        "--generate",
        "--generate-assets",
        "--load-db",
        "--train",
        "--lightgbm",
        "--mlflow",
        "--predict",
        "--predictions",
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

    def _stub_build(session: Any, **kwargs: Any) -> dict[str, Any]:
        captured.update(kwargs)
        return {
            "as_of_date": date(2025, 12, 31),
            "feature_version": "rainfall_risk_features_v1",
            "baseline_simulation_id": "DEFAULT_2025_BASELINE",
            "assets_considered": 5000,
            "records_generated": 5000,
            "records_inserted": 5000,
            "positive_targets": 125,
            "negative_targets": 4875,
            "positive_target_rate": 0.025,
            "feature_payload_key_count": 48,
            "categorical_encoder_counts": {
                "industry": 20,
                "business_type": 90,
                "postcode": 70,
                "lga_code": 48,
                "risk_band": 4,
            },
            "replace_existing": True,
        }

    def _stub_fetch(session: Any, **kwargs: Any) -> list[dict[str, Any]]:
        return [{"asset_id": f"VIC{i:04d}"} for i in range(1, 11)]

    monkeypatch.setattr("src.db.session.SessionLocal", lambda: _StubSession())
    monkeypatch.setattr(
        "src.cli.build_training_data.run_model_training_data_build", _stub_build
    )
    monkeypatch.setattr(
        "src.ml.dataset.fetch_model_training_inputs", _stub_fetch
    )

    rc = main(["--replace-existing"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "feature_version=rainfall_risk_features_v1" in out
    assert "generated=5000" in out
    assert "positive=125" in out
    assert "negative=4875" in out
    assert "train=" in out
    assert "test=" in out
    assert captured["feature_version"] == "rainfall_risk_features_v1"
    assert captured["replace_existing"] is True


def test_main_returns_nonzero_on_value_error(monkeypatch: pytest.MonkeyPatch) -> None:
    class _StubSession:
        def close(self) -> None:
            pass

    monkeypatch.setattr("src.db.session.SessionLocal", lambda: _StubSession())

    def _stub_raises(*args: Any, **kwargs: Any) -> dict[str, Any]:
        raise ValueError("No input rows for model_training_data build")

    monkeypatch.setattr(
        "src.cli.build_training_data.run_model_training_data_build", _stub_raises
    )

    rc = main([])
    assert rc == 2
