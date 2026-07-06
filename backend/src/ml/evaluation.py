"""Classification + ranking metric helpers and feature-importance extraction"""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Any

import numpy as np
from sklearn.metrics import (
    accuracy_score,
    average_precision_score,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)


def _to_float(value: Any) -> float | None:
    """Coerce a metric scalar to a plain Python float (or None)"""
    if value is None:
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(result):
        return None
    return result


def calculate_binary_classification_metrics(
    y_true: Sequence[int],
    y_probability: Sequence[float],
    threshold: float = 0.5,
) -> dict[str, float | None]:
    """Return ``accuracy / precision / recall / f1 / roc_auc / pr_auc``.

    ``roc_auc`` and ``pr_auc`` require both classes to appear in
    ``y_true``; otherwise they return ``None``
    """
    if len(y_true) != len(y_probability):
        raise ValueError(
            f"y_true ({len(y_true)}) and y_probability ({len(y_probability)}) "
            "must have the same length"
        )
    if not 0 <= threshold <= 1:
        raise ValueError(f"threshold must be in [0, 1] (got {threshold})")

    y_true_arr = np.asarray(list(y_true), dtype=int)
    y_prob_arr = np.asarray(list(y_probability), dtype=float)
    y_pred = (y_prob_arr >= threshold).astype(int)

    metrics: dict[str, float | None] = {
        "accuracy": _to_float(accuracy_score(y_true_arr, y_pred)) if len(y_true_arr) else None,
        "precision": _to_float(
            precision_score(y_true_arr, y_pred, zero_division=0)
        ) if len(y_true_arr) else None,
        "recall": _to_float(
            recall_score(y_true_arr, y_pred, zero_division=0)
        ) if len(y_true_arr) else None,
        "f1": _to_float(
            f1_score(y_true_arr, y_pred, zero_division=0)
        ) if len(y_true_arr) else None,
    }

    unique_classes = np.unique(y_true_arr) if len(y_true_arr) else np.array([])
    if unique_classes.size >= 2:
        metrics["roc_auc"] = _to_float(roc_auc_score(y_true_arr, y_prob_arr))
        metrics["pr_auc"] = _to_float(average_precision_score(y_true_arr, y_prob_arr))
    else:
        metrics["roc_auc"] = None
        metrics["pr_auc"] = None
    return metrics


def calculate_ranking_metrics(
    y_true: Sequence[int],
    y_probability: Sequence[float],
    top_fraction: float = 0.10,
) -> dict[str, float | None]:
    """Return ``precision_at_top_k / recall_at_top_k / lift_at_top_k`` metrics"""
    if not 0 < top_fraction < 1:
        raise ValueError(
            f"top_fraction must satisfy 0 < top_fraction < 1 (got {top_fraction})"
        )
    if len(y_true) != len(y_probability):
        raise ValueError(
            f"y_true ({len(y_true)}) and y_probability ({len(y_probability)}) "
            "must have the same length"
        )

    n = len(y_true)
    if n == 0:
        return {
            "precision_at_top_10_pct": None,
            "recall_at_top_10_pct": None,
            "lift_at_top_10_pct": None,
        }

    y_true_arr = np.asarray(list(y_true), dtype=int)
    y_prob_arr = np.asarray(list(y_probability), dtype=float)
    positives = int(y_true_arr.sum())
    positive_rate = positives / n if n else 0.0

    k = max(1, math.ceil(n * top_fraction))
    # Sort by probability descending. argsort is ascending → negate for descending
    order = np.argsort(-y_prob_arr, kind="mergesort")  # mergesort = stable
    top_k_idx = order[:k]
    top_k_positives = int(y_true_arr[top_k_idx].sum())

    precision_at_k = top_k_positives / k
    recall_at_k = (top_k_positives / positives) if positives > 0 else None
    lift_at_k = (precision_at_k / positive_rate) if positive_rate > 0 else None

    return {
        "precision_at_top_10_pct": _to_float(precision_at_k),
        "recall_at_top_10_pct": _to_float(recall_at_k) if recall_at_k is not None else None,
        "lift_at_top_10_pct": _to_float(lift_at_k) if lift_at_k is not None else None,
    }


def build_feature_importance_frame(
    model: Any,
    feature_names: Sequence[str],
) -> list[dict[str, Any]]:
    """Extract ``importance_gain`` + ``importance_split`` per feature"""
    booster = getattr(model, "booster_", None)
    if booster is None:
        raise ValueError(
            "Expected a fitted LightGBM model exposing `booster_`; got "
            f"{type(model).__name__}"
        )
    gains = booster.feature_importance(importance_type="gain")
    splits = booster.feature_importance(importance_type="split")
    if len(gains) != len(feature_names) or len(splits) != len(feature_names):
        raise ValueError(
            "feature_importance arrays do not match feature_names length"
        )
    out: list[dict[str, Any]] = []
    for name, gain, split in zip(feature_names, gains, splits, strict=True):
        out.append(
            {
                "feature": str(name),
                "importance_gain": float(gain),
                "importance_split": int(split),
            }
        )
    return out


__all__ = [
    "build_feature_importance_frame",
    "calculate_binary_classification_metrics",
    "calculate_ranking_metrics",
]
