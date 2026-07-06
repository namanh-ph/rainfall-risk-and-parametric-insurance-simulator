"""Canonical domain constants.

Values in this module are the single source of truth for thresholds, weights,
band names, and trigger statuses. Schema CHECK constraints, ORM models,
scoring code, payout code, and API responses must reference these names
rather than redefining the values inline
"""

from __future__ import annotations

from typing import Final

DEFAULT_SRID: Final[int] = 4326

RISK_BAND_LOW: Final[str] = "Low"
RISK_BAND_MEDIUM: Final[str] = "Medium"
RISK_BAND_HIGH: Final[str] = "High"
RISK_BAND_SEVERE: Final[str] = "Severe"

# Ordered tuple; stable iteration order for CHECK constraints, dropdowns, etc
RISK_BANDS: Final[tuple[str, ...]] = (
    RISK_BAND_LOW,
    RISK_BAND_MEDIUM,
    RISK_BAND_HIGH,
    RISK_BAND_SEVERE,
)

# Half-open range edges for each band:
#   Low:    0  <= risk_score < 25
#   Medium: 25 <= risk_score < 50
#   High:   50 <= risk_score < 75
#   Severe: 75 <= risk_score <= 100
RISK_BAND_THRESHOLDS: Final[tuple[tuple[str, float, float], ...]] = (
    (RISK_BAND_LOW, 0.0, 25.0),
    (RISK_BAND_MEDIUM, 25.0, 50.0),
    (RISK_BAND_HIGH, 50.0, 75.0),
    (RISK_BAND_SEVERE, 75.0, 100.0),
)

# station_confidence_weight = max(STATION_CONFIDENCE_FLOOR,
#                                 1; station_distance_km
#                                     / STATION_CONFIDENCE_DISTANCE_DIVISOR_KM)
STATION_CONFIDENCE_FLOOR: Final[float] = 0.50
STATION_CONFIDENCE_DISTANCE_DIVISOR_KM: Final[float] = 100.0

# Tuples are (min_mm_inclusive, max_mm_exclusive_or_None, payout_rate)
# Implementation lives in `insurance/`; constants are persistence-ready only
PAYOUT_TIERS: Final[tuple[tuple[float, float | None, float], ...]] = (
    (0.0, 100.0, 0.0),
    (100.0, 150.0, 0.2),
    (150.0, 200.0, 0.5),
    (200.0, None, 1.0),
)

# Default 3-day rainfall threshold above which an asset is considered to
# have been hit by an extreme rainfall event in feature engineering
EXTREME_RAINFALL_3D_MM: Final[float] = 100.0

# The schema persists the binary {triggered, not_triggered} encoding
# The richer 4-tier `none/partial_20/partial_50/full` encoding documented
# in `data_contracts.md` is reachable via `payout_rate`
TRIGGER_TRIGGERED: Final[str] = "triggered"
TRIGGER_NOT_TRIGGERED: Final[str] = "not_triggered"
TRIGGER_STATUSES: Final[tuple[str, ...]] = (TRIGGER_TRIGGERED, TRIGGER_NOT_TRIGGERED)

# Aliases; same values as TRIGGER_*
TRIGGER_STATUS_TRIGGERED: Final[str] = TRIGGER_TRIGGERED
TRIGGER_STATUS_NOT_TRIGGERED: Final[str] = TRIGGER_NOT_TRIGGERED

# Canonical payout threshold table
DEFAULT_PAYOUT_THRESHOLDS: Final[tuple[dict, ...]] = (
    {"min_rainfall_3d_mm": 0.0, "max_rainfall_3d_mm": 100.0, "payout_rate": 0.0},
    {"min_rainfall_3d_mm": 100.0, "max_rainfall_3d_mm": 150.0, "payout_rate": 0.2},
    {"min_rainfall_3d_mm": 150.0, "max_rainfall_3d_mm": 200.0, "payout_rate": 0.5},
    {"min_rainfall_3d_mm": 200.0, "max_rainfall_3d_mm": None, "payout_rate": 1.0},
)

DEFAULT_PAYOUT_SIMULATION_ID: Final[str] = "DEFAULT_2025_BASELINE"
DEFAULT_PAYOUT_SIMULATION_NAME: Final[str] = (
    "Default 2025 baseline parametric payout simulation"
)
DEFAULT_PAYOUT_COVERAGE_MULTIPLIER: Final[float] = 1.0
