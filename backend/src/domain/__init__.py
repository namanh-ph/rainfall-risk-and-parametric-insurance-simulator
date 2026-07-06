"""Domain constants and shared value objects.

This package owns thresholds, enums, and weights that the schema, scoring,
payout, and ML layers share. Implementation logic lives in the dedicated
modules (`risk/`, `insurance/`, `features/`); this package is value-only
"""

from src.domain.constants import (
    DEFAULT_SRID,
    PAYOUT_TIERS,
    RISK_BAND_HIGH,
    RISK_BAND_LOW,
    RISK_BAND_MEDIUM,
    RISK_BAND_SEVERE,
    RISK_BANDS,
    STATION_CONFIDENCE_DISTANCE_DIVISOR_KM,
    STATION_CONFIDENCE_FLOOR,
    TRIGGER_NOT_TRIGGERED,
    TRIGGER_STATUSES,
    TRIGGER_TRIGGERED,
)

__all__ = [
    "DEFAULT_SRID",
    "PAYOUT_TIERS",
    "RISK_BANDS",
    "RISK_BAND_HIGH",
    "RISK_BAND_LOW",
    "RISK_BAND_MEDIUM",
    "RISK_BAND_SEVERE",
    "STATION_CONFIDENCE_DISTANCE_DIVISOR_KM",
    "STATION_CONFIDENCE_FLOOR",
    "TRIGGER_NOT_TRIGGERED",
    "TRIGGER_STATUSES",
    "TRIGGER_TRIGGERED",
]
