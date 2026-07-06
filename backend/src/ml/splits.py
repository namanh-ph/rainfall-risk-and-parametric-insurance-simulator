"""Deterministic train/test split helpers (no model training).

Splits are computed from a SHA-256 hash of ``(asset_id, seed)`` so the
assignment is:

- deterministic for the same ``(asset_id, test_size, seed)``,
; independent of row order (each asset is hashed in isolation),
; changes for some assets when ``seed`` changes (with overwhelming
  probability for any reasonable portfolio size)
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable
from typing import Any

from src.schemas.ml_dataset import TrainTestSplitSummary


def _validate_test_size(test_size: float) -> None:
    if not 0 < test_size < 1:
        raise ValueError(
            f"test_size must satisfy 0 < test_size < 1 (got {test_size})"
        )


def assign_train_test_split(
    asset_id: str,
    test_size: float = 0.2,
    seed: int = 42,
) -> str:
    """Return 'train' or 'test' for a single asset deterministically"""
    if not asset_id:
        raise ValueError("asset_id must be non-empty")
    _validate_test_size(test_size)
    digest = hashlib.sha256(f"{asset_id}:{seed}".encode()).digest()
    bucket = int.from_bytes(digest[:8], "big") / 2**64
    return "test" if bucket < test_size else "train"


def summarise_train_test_split(
    records: Iterable[dict[str, Any]],
    test_size: float = 0.2,
    seed: int = 42,
) -> dict[str, Any]:
    """Aggregate per-asset split assignment into a summary dict"""
    _validate_test_size(test_size)
    train_count = 0
    test_count = 0
    for record in records:
        asset_id = str(record.get("asset_id", ""))
        if not asset_id:
            raise ValueError("Every record must have a non-empty asset_id")
        split = assign_train_test_split(asset_id, test_size=test_size, seed=seed)
        if split == "test":
            test_count += 1
        else:
            train_count += 1
    total = train_count + test_count
    test_rate = (test_count / total) if total else 0.0
    summary = {
        "train_count": train_count,
        "test_count": test_count,
        "total_count": total,
        "test_rate": round(test_rate, 6),
        "seed": seed,
        "test_size": test_size,
    }
    TrainTestSplitSummary.model_validate(summary)
    return summary


__all__ = ["assign_train_test_split", "summarise_train_test_split"]
