"""Tests for ML evaluation metrics"""

from __future__ import annotations

import numpy as np
import pytest

from src.ml.evaluation import (
    build_feature_importance_frame,
    calculate_binary_classification_metrics,
    calculate_ranking_metrics,
)


def test_metrics_returns_accuracy_precision_recall_f1() -> None:
    y_true = [0, 0, 1, 1, 1]
    y_prob = [0.1, 0.4, 0.6, 0.7, 0.9]
    m = calculate_binary_classification_metrics(y_true, y_prob, threshold=0.5)
    assert m["accuracy"] == 1.0
    assert m["precision"] == 1.0
    assert m["recall"] == 1.0
    assert m["f1"] == 1.0


def test_metrics_roc_and_pr_auc_when_both_classes_present() -> None:
    y_true = [0, 0, 1, 1, 1]
    y_prob = [0.1, 0.4, 0.6, 0.7, 0.9]
    m = calculate_binary_classification_metrics(y_true, y_prob)
    assert m["roc_auc"] is not None
    assert 0 <= m["roc_auc"] <= 1
    assert m["pr_auc"] is not None
    assert 0 <= m["pr_auc"] <= 1


def test_metrics_roc_and_pr_auc_null_when_only_one_class() -> None:
    y_true = [0, 0, 0, 0]
    y_prob = [0.1, 0.2, 0.3, 0.4]
    m = calculate_binary_classification_metrics(y_true, y_prob)
    assert m["roc_auc"] is None
    assert m["pr_auc"] is None


def test_metrics_rejects_length_mismatch() -> None:
    with pytest.raises(ValueError):
        calculate_binary_classification_metrics([0, 1], [0.1, 0.2, 0.3])


def test_metrics_rejects_invalid_threshold() -> None:
    with pytest.raises(ValueError):
        calculate_binary_classification_metrics([0, 1], [0.1, 0.9], threshold=1.5)


def test_ranking_metrics_precision_at_top_decile_with_perfect_signal() -> None:
    # 100 rows, top 10 all positives → precision@10pct = 1.0
    y_true = [1] * 10 + [0] * 90
    y_prob = sorted(np.linspace(0, 1, 100), reverse=True)
    m = calculate_ranking_metrics(y_true, y_prob, top_fraction=0.10)
    assert m["precision_at_top_10_pct"] == 1.0
    assert m["recall_at_top_10_pct"] == 1.0
    assert m["lift_at_top_10_pct"] == pytest.approx(10.0, abs=1e-6)


def test_ranking_metrics_no_positives_returns_null_recall_and_lift() -> None:
    y_true = [0] * 50
    y_prob = list(np.linspace(0, 1, 50))
    m = calculate_ranking_metrics(y_true, y_prob)
    assert m["recall_at_top_10_pct"] is None
    assert m["lift_at_top_10_pct"] is None
    # precision_at_top_10_pct is computable but should be 0 (no positives in top k)
    assert m["precision_at_top_10_pct"] == 0.0


def test_ranking_metrics_handles_empty_input() -> None:
    m = calculate_ranking_metrics([], [])
    assert m["precision_at_top_10_pct"] is None
    assert m["recall_at_top_10_pct"] is None
    assert m["lift_at_top_10_pct"] is None


def test_ranking_metrics_rejects_invalid_top_fraction() -> None:
    with pytest.raises(ValueError):
        calculate_ranking_metrics([0, 1], [0.1, 0.9], top_fraction=0.0)
    with pytest.raises(ValueError):
        calculate_ranking_metrics([0, 1], [0.1, 0.9], top_fraction=1.0)


def test_build_feature_importance_frame_returns_canonical_records() -> None:
    import lightgbm as lgb

    X = np.array([[0.1, 0.2], [0.5, 0.4], [0.9, 0.7], [0.3, 0.5]] * 25)
    y = ([0, 0, 1, 1]) * 25
    model = lgb.LGBMClassifier(n_estimators=10, num_leaves=4, random_state=42, verbose=-1)
    model.fit(X, y)
    out = build_feature_importance_frame(model, ["a", "b"])
    assert {row["feature"] for row in out} == {"a", "b"}
    for row in out:
        assert set(row.keys()) == {"feature", "importance_gain", "importance_split"}
        assert row["importance_gain"] >= 0
        assert row["importance_split"] >= 0


def test_build_feature_importance_frame_rejects_non_lightgbm_model() -> None:
    class _NotAModel:
        pass

    with pytest.raises(ValueError, match="booster_"):
        build_feature_importance_frame(_NotAModel(), ["a", "b"])
