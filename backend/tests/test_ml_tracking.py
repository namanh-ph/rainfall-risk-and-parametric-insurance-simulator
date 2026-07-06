"""Tests for the MLflow tracking helpers"""

from __future__ import annotations

import sys
import types
from pathlib import Path
from typing import Any

import pytest

from src.ml import tracking as tracking_module
from src.ml.tracking import (
    configure_mlflow,
    get_mlflow_tracking_uri,
    log_training_run_to_mlflow,
)


def test_get_mlflow_tracking_uri_returns_configured_value(monkeypatch: pytest.MonkeyPatch) -> None:
    class _Settings:
        MLFLOW_TRACKING_URI = "http://mlflow.example/"

    monkeypatch.setattr(tracking_module, "get_settings", lambda: _Settings())
    assert get_mlflow_tracking_uri() == "http://mlflow.example/"


def test_configure_mlflow_does_not_raise_when_mlflow_installed() -> None:
    # mlflow is a declared dep; calling configure should be silent + idempotent
    configure_mlflow(tracking_uri="file:./mlruns", experiment_name="test-experiment")


class _StubRun:
    def __init__(self, run_id: str = "stub-run-id") -> None:
        self.info = types.SimpleNamespace(run_id=run_id)

    def __enter__(self) -> _StubRun:
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None


def _install_stub_mlflow(monkeypatch: pytest.MonkeyPatch, *, fail: bool = False) -> dict[str, Any]:
    captured: dict[str, Any] = {"params": None, "metrics": None, "artifacts": []}

    def _set_uri(uri: str) -> None:
        captured["tracking_uri"] = uri

    def _set_experiment(name: str) -> None:
        captured["experiment_name"] = name

    def _start_run():
        if fail:
            raise RuntimeError("simulated mlflow failure")
        return _StubRun()

    def _log_params(params: dict[str, Any]) -> None:
        captured["params"] = dict(params)

    def _log_metrics(metrics: dict[str, float]) -> None:
        captured["metrics"] = dict(metrics)

    def _log_artifact(path: str) -> None:
        captured["artifacts"].append(path)

    def _log_model(model: Any, artifact_path: str) -> None:
        captured["model_logged"] = True

    stub = types.SimpleNamespace(
        set_tracking_uri=_set_uri,
        set_experiment=_set_experiment,
        start_run=_start_run,
        log_params=_log_params,
        log_metrics=_log_metrics,
        log_artifact=_log_artifact,
        lightgbm=types.SimpleNamespace(log_model=_log_model),
    )
    monkeypatch.setitem(sys.modules, "mlflow", stub)
    return captured


def test_log_training_run_returns_mlflow_logged_true_on_success(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    captured = _install_stub_mlflow(monkeypatch)
    artefact = tmp_path / "model.pkl"
    artefact.write_bytes(b"stub")

    result = log_training_run_to_mlflow(
        params={"n_estimators": 200, "learning_rate": 0.05},
        metrics={"roc_auc": 0.83, "pr_auc": 0.21, "missing": None},
        artifacts={"model": artefact},
        model=object(),
        experiment_name="test-experiment",
    )

    assert result["mlflow_logged"] is True
    assert result["mlflow_run_id"] == "stub-run-id"
    assert captured["params"] == {"n_estimators": "200", "learning_rate": "0.05"}
    assert "roc_auc" in captured["metrics"]
    assert "missing" not in captured["metrics"]  # None values dropped
    assert str(artefact) in captured["artifacts"]
    assert captured.get("model_logged") is True


def test_log_training_run_returns_mlflow_logged_false_and_warning_on_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _install_stub_mlflow(monkeypatch, fail=True)
    artefact = tmp_path / "model.pkl"
    artefact.write_bytes(b"stub")

    result = log_training_run_to_mlflow(
        params={"a": 1},
        metrics={"roc_auc": 0.5},
        artifacts={"model": artefact},
    )
    assert result["mlflow_logged"] is False
    assert result["mlflow_run_id"] is None
    assert "warning" in result
    assert "simulated mlflow failure" in result["warning"]
    # Local artefact must still exist after a tracking failure
    assert artefact.exists()


def test_log_training_run_returns_warning_when_mlflow_missing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # Make `import mlflow` raise ImportError
    monkeypatch.setitem(sys.modules, "mlflow", None)
    artefact = tmp_path / "model.pkl"
    artefact.write_bytes(b"stub")
    result = log_training_run_to_mlflow(
        params={}, metrics={}, artifacts={"model": artefact}
    )
    assert result["mlflow_logged"] is False
    assert "warning" in result
    assert artefact.exists()
