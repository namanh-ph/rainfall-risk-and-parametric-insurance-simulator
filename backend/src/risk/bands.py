"""Risk-band assignment.

Half-open ranges:

- Low     : 0  <= risk_score < 25
- Medium  : 25 <= risk_score < 50
- High    : 50 <= risk_score < 75
- Severe  : 75 <= risk_score <= 100
"""

from __future__ import annotations

from src.domain.constants import (
    RISK_BAND_HIGH,
    RISK_BAND_LOW,
    RISK_BAND_MEDIUM,
    RISK_BAND_SEVERE,
)


def assign_risk_band(risk_score: float) -> str:
    """Map a numeric risk score in [0, 100] to its band."""
    if not 0 <= risk_score <= 100:
        raise ValueError(
            f"risk_score must be in [0, 100] (got {risk_score})"
        )
    if risk_score < 25:
        return RISK_BAND_LOW
    if risk_score < 50:
        return RISK_BAND_MEDIUM
    if risk_score < 75:
        return RISK_BAND_HIGH
    return RISK_BAND_SEVERE


__all__ = ["assign_risk_band"]
