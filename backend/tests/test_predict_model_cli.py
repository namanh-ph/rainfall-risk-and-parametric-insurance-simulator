"""Tests for the batch prediction CLI"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

import pytest

from src.cli.predict_model import _resolve_asset_ids, build_parser, main


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


def test_parser_default_feature_version() -> None:
    args = build_parser().parse_args([])
    assert args.feature_version == "rainfall_risk_features_v1"


def test_parser_default_model_name_and_version() -> None:
    args = build_parser().parse_args([])
    assert args.model_name == "rainfall_risk_lgbm"
    assert args.model_version == "v1"


def test_parser_supports_custom_artifact_dir() -> None:
    args = build_parser().parse_args(["--artifact-dir", "/tmp/custom"])
    assert str(args.artifact_dir) == str(Path("/tmp/custom"))


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
        "--train",
        "--lightgbm",
        "--mlflow",
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

    def _stub_run(session: Any, **kwargs: Any) -> dict[str, Any]:
        captured.update(kwargs)
        return {
            "model_name": "rainfall_risk_lgbm",
            "model_version": "v1",
            "as_of_date": date(2025, 12, 31),
            "feature_version": "rainfall_risk_features_v1",
            "artifact_dir": "backend/artifacts/models/rainfall_risk_lgbm_v1_2025-12-31",
            "records_loaded": 5000,
            "prediction_records_generated": 5000,
            "prediction_records_inserted": 5000,
            "min_probability": 0.001,
            "median_probability": 0.024,
            "max_probability": 0.91,
            "top_ranked_asset_id": "VIC0123",
            "top_risk_driver_counts": {
                "rainfall_percentile": 3000,
                "rainfall_3d_to_p95_ratio": 1500,
                "exposure_weight": 500,
            },
            "warnings": [],
            "replace_existing": True,
        }

    monkeypatch.setattr("src.db.session.SessionLocal", lambda: _StubSession())
    monkeypatch.setattr("src.cli.predict_model.run_batch_prediction", _stub_run)

    rc = main(["--replace-existing"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "model=rainfall_risk_lgbm/v1" in out
    assert "records=5000" in out
    assert "inserted=5000" in out
    assert "top=VIC0123" in out
    assert captured["model_name"] == "rainfall_risk_lgbm"
    assert captured["model_version"] == "v1"
    assert captured["replace_existing"] is True


def test_main_returns_nonzero_on_file_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    class _StubSession:
        def close(self) -> None:
            pass

    monkeypatch.setattr("src.db.session.SessionLocal", lambda: _StubSession())

    def _stub_raises(*args: Any, **kwargs: Any) -> dict[str, Any]:
        raise FileNotFoundError("model.pkl missing")

    monkeypatch.setattr("src.cli.predict_model.run_batch_prediction", _stub_raises)

    rc = main([])
    assert rc == 2


def test_main_returns_nonzero_on_value_error(monkeypatch: pytest.MonkeyPatch) -> None:
    class _StubSession:
        def close(self) -> None:
            pass

    monkeypatch.setattr("src.db.session.SessionLocal", lambda: _StubSession())

    def _stub_raises(*args: Any, **kwargs: Any) -> dict[str, Any]:
        raise ValueError("No model_training_data rows available")

    monkeypatch.setattr("src.cli.predict_model.run_batch_prediction", _stub_raises)

    rc = main([])
    assert rc == 2
