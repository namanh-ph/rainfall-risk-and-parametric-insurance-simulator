"""Tests for the LightGBM training CLI."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

import pytest

from src.cli.train_model import _resolve_asset_ids, build_parser, main


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


def test_parser_defaults() -> None:
    args = build_parser().parse_args([])
    assert args.as_of_date == date(2025, 12, 31)
    assert args.feature_version == "rainfall_risk_features_v1"
    assert args.model_name == "rainfall_risk_lgbm"
    assert args.model_version == "v1"
    assert args.test_size == 0.2
    assert args.split_seed == 42
    assert args.random_state == 42
    assert args.experiment_name == "simulator-risk-ranking"
    assert args.log_to_mlflow is True
    assert args.output_dir is None


def test_parser_accepts_custom_as_of_date() -> None:
    args = build_parser().parse_args(["--as-of-date", "2024-06-30"])
    assert args.as_of_date == date(2024, 6, 30)


def test_parser_accepts_custom_model_metadata() -> None:
    args = build_parser().parse_args(
        ["--model-name", "custom_model", "--model-version", "v3.5"]
    )
    assert args.model_name == "custom_model"
    assert args.model_version == "v3.5"


def test_parser_accepts_custom_split_and_random_state() -> None:
    args = build_parser().parse_args(
        ["--test-size", "0.3", "--split-seed", "7", "--random-state", "99"]
    )
    assert args.test_size == 0.3
    assert args.split_seed == 7
    assert args.random_state == 99


def test_parser_accepts_custom_output_dir() -> None:
    args = build_parser().parse_args(["--output-dir", "/tmp/custom_artefacts"])
    assert isinstance(args.output_dir, Path)
    assert str(args.output_dir).endswith("custom_artefacts")


def test_parser_accepts_custom_experiment_name() -> None:
    args = build_parser().parse_args(["--experiment-name", "alt-experiment"])
    assert args.experiment_name == "alt-experiment"


def test_parser_supports_log_to_mlflow_flag() -> None:
    args = build_parser().parse_args(["--log-to-mlflow"])
    assert args.log_to_mlflow is True


def test_parser_supports_no_mlflow_flag() -> None:
    args = build_parser().parse_args(["--no-mlflow"])
    assert args.log_to_mlflow is False


def test_parser_does_not_expose_forbidden_options() -> None:
    parser = build_parser()
    flags = {a.option_strings[0] for a in parser._actions if a.option_strings}
    forbidden = {
        "--n-assets",
        "--generate",
        "--generate-assets",
        "--load-db",
        "--predict",
        "--predictions",
        "--simulate",
        "--payouts",
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

    def _stub_train(session: Any, **kwargs: Any) -> dict[str, Any]:
        captured.update(kwargs)
        return {
            "model_name": "rainfall_risk_lgbm",
            "model_version": "v1",
            "as_of_date": date(2025, 12, 31),
            "feature_version": "rainfall_risk_features_v1",
            "target_name": "target_extreme_rainfall_event",
            "train_row_count": 4000,
            "test_row_count": 1000,
            "feature_count": 48,
            "positive_count": 125,
            "negative_count": 4875,
            "positive_rate": 0.025,
            "metrics": {
                "roc_auc": 0.83,
                "pr_auc": 0.21,
                "precision_at_top_10_pct": 0.18,
                "recall_at_top_10_pct": 0.72,
                "lift_at_top_10_pct": 7.2,
            },
            "top_features": [
                {"feature": "rainfall_percentile", "importance_gain": 123.4, "importance_split": 19}
            ],
            "artifact_path": "backend/artifacts/models/rainfall_risk_lgbm_v1_2025-12-31",
            "mlflow_logged": True,
            "mlflow_run_id": "abcd",
            "warnings": [],
        }

    monkeypatch.setattr("src.db.session.SessionLocal", lambda: _StubSession())
    monkeypatch.setattr("src.cli.train_model.run_lightgbm_training", _stub_train)

    rc = main([])
    assert rc == 0
    out = capsys.readouterr().out
    assert "model=rainfall_risk_lgbm/v1" in out
    assert "train=4000" in out
    assert "test=1000" in out
    assert "features=48" in out
    assert "roc_auc=0.83" in out
    assert "rainfall_percentile" in out
    assert captured["as_of_date"] == date(2025, 12, 31)
    assert captured["model_name"] == "rainfall_risk_lgbm"


def test_main_returns_nonzero_on_value_error(monkeypatch: pytest.MonkeyPatch) -> None:
    class _StubSession:
        def close(self) -> None:
            pass

    monkeypatch.setattr("src.db.session.SessionLocal", lambda: _StubSession())

    def _stub_raises(*args: Any, **kwargs: Any) -> dict[str, Any]:
        raise ValueError("No model_training_data rows")

    monkeypatch.setattr("src.cli.train_model.run_lightgbm_training", _stub_raises)
    rc = main([])
    assert rc == 2
