"""MLflow tracking helpers with graceful local-only fallback."""

from __future__ import annotations

import logging
import math
from typing import Any

from src.core.config import get_settings

logger = logging.getLogger(__name__)

DEFAULT_EXPERIMENT_NAME = "simulator-risk-ranking"


def get_mlflow_tracking_uri() -> str:
    """Return the configured MLflow tracking URI."""
    return get_settings().MLFLOW_TRACKING_URI


def configure_mlflow(
    tracking_uri: str | None = None,
    experiment_name: str = DEFAULT_EXPERIMENT_NAME,
) -> None:
    """Set the MLflow tracking URI + experiment; never raises."""
    try:
        import mlflow
    except ImportError:  # pragma: no cover - mlflow is a declared dep
        logger.warning("mlflow is not installed; configure_mlflow is a no-op")
        return

    try:
        uri = tracking_uri or get_mlflow_tracking_uri()
        mlflow.set_tracking_uri(uri)
        mlflow.set_experiment(experiment_name)
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("configure_mlflow failed: %s", exc)


def _scalar_metric(value: Any) -> float | None:
    if value is None:
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(out):
        return None
    return out


def log_training_run_to_mlflow(
    params: dict[str, Any],
    metrics: dict[str, Any],
    artifacts: dict[str, Any],
    model: Any = None,
    experiment_name: str = DEFAULT_EXPERIMENT_NAME,
) -> dict[str, Any]:
    """Log one training run to MLflow. Returns status dict; never raises.

    A failure (no tracking server, import error, log error, …) is captured
    in the returned dict as ``mlflow_logged=False`` and a ``warning`` field
    so the caller can keep the local artefacts.
    """
    tracking_uri = get_mlflow_tracking_uri()
    try:
        import mlflow
    except ImportError as exc:
        return {
            "mlflow_logged": False,
            "mlflow_run_id": None,
            "mlflow_tracking_uri": tracking_uri,
            "warning": f"mlflow not installed: {exc}",
        }

    try:
        mlflow.set_tracking_uri(tracking_uri)
        mlflow.set_experiment(experiment_name)
        scalar_metrics = {
            k: v
            for k, v in (
                (key, _scalar_metric(value)) for key, value in metrics.items()
            )
            if v is not None
        }
        with mlflow.start_run() as run:
            if params:
                mlflow.log_params(
                    {k: str(v) for k, v in params.items() if v is not None}
                )
            if scalar_metrics:
                mlflow.log_metrics(scalar_metrics)
            for _name, path in artifacts.items():
                try:
                    mlflow.log_artifact(str(path))
                except Exception as artefact_exc:  # pragma: no cover
                    logger.warning(
                        "MLflow log_artifact(%s) failed: %s", path, artefact_exc
                    )
            if model is not None:
                try:
                    mlflow.lightgbm.log_model(model, artifact_path="model")
                except Exception as model_exc:  # pragma: no cover
                    logger.warning("MLflow log_model failed: %s", model_exc)
            return {
                "mlflow_logged": True,
                "mlflow_run_id": run.info.run_id,
                "mlflow_tracking_uri": tracking_uri,
            }
    except Exception as exc:
        return {
            "mlflow_logged": False,
            "mlflow_run_id": None,
            "mlflow_tracking_uri": tracking_uri,
            "warning": f"MLflow logging failed: {exc}",
        }


__all__ = [
    "DEFAULT_EXPERIMENT_NAME",
    "configure_mlflow",
    "get_mlflow_tracking_uri",
    "log_training_run_to_mlflow",
]
