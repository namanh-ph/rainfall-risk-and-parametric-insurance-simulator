"""Tests for the deterministic train/test split helpers"""

from __future__ import annotations

import pytest

from src.ml.splits import assign_train_test_split, summarise_train_test_split


def test_assign_returns_train_or_test() -> None:
    for i in range(20):
        result = assign_train_test_split(f"VIC{i:04d}")
        assert result in {"train", "test"}


def test_assign_is_deterministic() -> None:
    for i in range(50):
        asset_id = f"VIC{i:04d}"
        a = assign_train_test_split(asset_id, test_size=0.3, seed=7)
        b = assign_train_test_split(asset_id, test_size=0.3, seed=7)
        assert a == b


def test_assign_changes_for_some_records_when_seed_changes() -> None:
    a = [assign_train_test_split(f"VIC{i:04d}", seed=42) for i in range(1, 101)]
    b = [assign_train_test_split(f"VIC{i:04d}", seed=43) for i in range(1, 101)]
    assert a != b
    # At least 10% of assets should switch sides for a different seed (sanity check)
    diff = sum(1 for x, y in zip(a, b) if x != y)
    assert diff >= 10


@pytest.mark.parametrize("size", [0.0, -0.01, 1.0, 1.5])
def test_assign_rejects_invalid_test_size(size: float) -> None:
    with pytest.raises(ValueError):
        assign_train_test_split("VIC0001", test_size=size)


def test_assign_does_not_depend_on_row_order() -> None:
    asset_ids = [f"VIC{i:04d}" for i in range(1, 51)]
    forward = [assign_train_test_split(aid, seed=1) for aid in asset_ids]
    backward = [assign_train_test_split(aid, seed=1) for aid in reversed(asset_ids)]
    # Reverse the second list and compare element-wise → equal
    assert forward == list(reversed(backward))


def test_summarise_counts_are_internally_consistent() -> None:
    records = [{"asset_id": f"VIC{i:04d}"} for i in range(1, 1001)]
    summary = summarise_train_test_split(records, test_size=0.2, seed=42)
    assert summary["train_count"] + summary["test_count"] == summary["total_count"]
    assert summary["total_count"] == 1000


def test_summarise_test_rate_between_zero_and_one() -> None:
    records = [{"asset_id": f"VIC{i:04d}"} for i in range(1, 501)]
    for size in (0.1, 0.2, 0.5, 0.8):
        summary = summarise_train_test_split(records, test_size=size, seed=42)
        assert 0 <= summary["test_rate"] <= 1


def test_summarise_test_rate_close_to_target_for_large_samples() -> None:
    records = [{"asset_id": f"VIC{i:05d}"} for i in range(1, 5001)]
    summary = summarise_train_test_split(records, test_size=0.2, seed=42)
    # With 5000 deterministic hashes, the empirical test rate should land
    # within a few percentage points of the target
    assert 0.17 <= summary["test_rate"] <= 0.23


def test_summarise_rejects_invalid_test_size() -> None:
    records = [{"asset_id": "VIC0001"}]
    with pytest.raises(ValueError):
        summarise_train_test_split(records, test_size=0.0)
    with pytest.raises(ValueError):
        summarise_train_test_split(records, test_size=1.0)


def test_summarise_rejects_record_without_asset_id() -> None:
    with pytest.raises(ValueError, match="non-empty asset_id"):
        summarise_train_test_split([{"asset_id": ""}])
