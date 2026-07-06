"""Tests for risk-band assignment"""

from __future__ import annotations

import pytest

from src.risk.bands import assign_risk_band


@pytest.mark.parametrize(
    ("score", "expected"),
    [
        (0, "Low"),
        (24.999, "Low"),
        (25, "Medium"),
        (49.999, "Medium"),
        (50, "High"),
        (74.999, "High"),
        (75, "Severe"),
        (100, "Severe"),
    ],
)
def test_assign_risk_band_at_canonical_boundaries(score: float, expected: str) -> None:
    assert assign_risk_band(score) == expected


def test_assign_risk_band_rejects_negative_score() -> None:
    with pytest.raises(ValueError):
        assign_risk_band(-0.01)


def test_assign_risk_band_rejects_score_above_100() -> None:
    with pytest.raises(ValueError):
        assign_risk_band(100.01)


def test_assign_risk_band_returns_canonical_string_constants() -> None:
    # Risk band string values must match the domain constants exactly
    from src.domain.constants import (
        RISK_BAND_HIGH,
        RISK_BAND_LOW,
        RISK_BAND_MEDIUM,
        RISK_BAND_SEVERE,
    )

    assert assign_risk_band(0) == RISK_BAND_LOW
    assert assign_risk_band(25) == RISK_BAND_MEDIUM
    assert assign_risk_band(50) == RISK_BAND_HIGH
    assert assign_risk_band(75) == RISK_BAND_SEVERE
