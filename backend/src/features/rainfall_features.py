"""Rainfall feature engineering.

Each asset's matched rainfall station drives a deterministic feature row:

- Trailing 1d/3d/7d/30d totals ending on ``as_of_date``
- Station-level p95, p99, max, and days-above-p95 over the 365-day lookback
- Asset rainfall_3d_mm percentile rank against rolling 3-day station totals
- ``extreme_rainfall_flag`` (feature only - does not assign risk band or trigger payouts)

Calculations are pure Python for transparency and testability. The data
access layer issues a parameterised PostGIS query via SQLAlchemy text.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable, Sequence
from datetime import date, timedelta
from typing import Any

from sqlalchemy import bindparam, delete, func, select, text, tuple_
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import TextClause

from src.db.models import Asset, AssetStationMapping, RainfallFeature
from src.schemas.rainfall_features import (
    RainfallFeatureRecord,
    RainfallFeatureRunSummary,
)

logger = logging.getLogger(__name__)

DEFAULT_AS_OF_DATE = date(2025, 12, 31)
LOOKBACK_DAYS = 365
EXTREME_PERCENTILE_THRESHOLD = 0.95
EXTREME_P95_MULTIPLIER = 3.0


def _percentile(values: Sequence[float], p: float) -> float:
    """Linear-interpolation percentile (matches numpy default)."""
    if not values:
        raise ValueError("percentile undefined for an empty sequence")
    if not 0 <= p <= 1:
        raise ValueError(f"p must be in [0, 1] (got {p})")
    sorted_values = sorted(values)
    n = len(sorted_values)
    if n == 1:
        return float(sorted_values[0])
    k = p * (n - 1)
    f = int(k)
    c = min(f + 1, n - 1)
    if f == c:
        return float(sorted_values[f])
    fraction = k - f
    return float(sorted_values[f] + fraction * (sorted_values[c] - sorted_values[f]))


def calculate_percentile_rank(value: float, distribution: Sequence[float]) -> float:
    """Return the proportion of ``distribution`` values <= ``value`` in [0, 1].

    Ties: every distribution element exactly equal to ``value`` counts toward
    the numerator. Therefore if all values match, the rank is 1.0; if every
    distribution value is strictly greater than ``value``, the rank is 0.0.
    """
    if not distribution:
        return 0.0
    n = len(distribution)
    le_count = sum(1 for d in distribution if d <= value)
    return le_count / n


def calculate_station_daily_statistics(
    observations: Iterable[dict[str, Any]],
) -> dict[str, Any]:
    """Compute station-relative statistics from daily rainfall observations."""
    daily_values = [float(o["rainfall_mm"]) for o in observations]
    if not daily_values:
        return {
            "rainfall_p95_station": None,
            "rainfall_p99_station": None,
            "max_365d_rainfall_mm": None,
            "days_above_p95_365d": None,
            "observation_count": 0,
        }
    p95 = _percentile(daily_values, 0.95)
    p99 = _percentile(daily_values, 0.99)
    max_value = max(daily_values)
    days_above_p95 = sum(1 for v in daily_values if v > p95)
    return {
        "rainfall_p95_station": round(p95, 4),
        "rainfall_p99_station": round(p99, 4),
        "max_365d_rainfall_mm": round(max_value, 4),
        "days_above_p95_365d": int(days_above_p95),
        "observation_count": len(daily_values),
    }


def _trailing_sum(
    obs_by_date: dict[date, float], as_of_date: date, days: int
) -> float:
    """Sum daily rainfall over the trailing ``days``-window ending on as_of_date.

    Missing dates contribute 0.0 — a defensive default for partial input.
    """
    start = as_of_date - timedelta(days=days - 1)
    total = 0.0
    current = start
    while current <= as_of_date:
        total += obs_by_date.get(current, 0.0)
        current += timedelta(days=1)
    return round(total, 4)


def calculate_trailing_rainfall_totals(
    observations: Iterable[dict[str, Any]],
    as_of_date: date,
) -> dict[str, float]:
    """Return 1d, 3d, 7d, and 30d trailing totals ending on ``as_of_date``."""
    obs_by_date: dict[date, float] = {}
    for o in observations:
        d = o["observation_date"]
        if not isinstance(d, date):
            d = date.fromisoformat(str(d))
        obs_by_date[d] = float(o["rainfall_mm"])
    return {
        "rainfall_1d_mm": _trailing_sum(obs_by_date, as_of_date, 1),
        "rainfall_3d_mm": _trailing_sum(obs_by_date, as_of_date, 3),
        "rainfall_7d_mm": _trailing_sum(obs_by_date, as_of_date, 7),
        "rainfall_30d_mm": _trailing_sum(obs_by_date, as_of_date, 30),
    }


def calculate_station_rolling_3d_totals(
    observations: Iterable[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Return a list of `{observation_date, rolling_3d_mm}` rows.

    Output is sorted by observation_date and contains one entry per
    available trailing-3-day window (i.e. starts from the third date for
    which observations exist consecutively).
    """
    pairs = sorted(
        (
            (
                o["observation_date"]
                if isinstance(o["observation_date"], date)
                else date.fromisoformat(str(o["observation_date"])),
                float(o["rainfall_mm"]),
            )
            for o in observations
        ),
        key=lambda x: x[0],
    )
    if len(pairs) < 3:
        return []

    obs_by_date = dict(pairs)
    out: list[dict[str, Any]] = []
    for d, _ in pairs:
        d1 = d
        d2 = d - timedelta(days=1)
        d3 = d - timedelta(days=2)
        if d2 in obs_by_date and d3 in obs_by_date:
            total = obs_by_date[d3] + obs_by_date[d2] + obs_by_date[d1]
            out.append({"observation_date": d, "rolling_3d_mm": round(total, 4)})
    return out


def calculate_asset_rainfall_feature_record(
    asset_id: str,
    station_id: str,
    observations: Sequence[dict[str, Any]],
    as_of_date: date,
) -> dict[str, Any]:
    """Build the rainfall_features record for a single asset.

    Raises ``ValueError`` if ``observations`` is empty (caller decides
    whether to count the asset as `assets_without_observations` or surface
    the error).
    """
    if not observations:
        raise ValueError(
            f"No rainfall observations for asset_id={asset_id} "
            f"station_id={station_id}"
        )

    trailing = calculate_trailing_rainfall_totals(observations, as_of_date)
    stats = calculate_station_daily_statistics(observations)
    rolling = calculate_station_rolling_3d_totals(observations)

    rainfall_3d_mm = trailing["rainfall_3d_mm"]
    if rolling:
        rolling_values = [r["rolling_3d_mm"] for r in rolling]
        rainfall_percentile: float | None = round(
            calculate_percentile_rank(rainfall_3d_mm, rolling_values), 4
        )
    else:
        rainfall_percentile = None

    p95 = stats["rainfall_p95_station"]
    extreme = (
        rainfall_percentile is not None
        and rainfall_percentile >= EXTREME_PERCENTILE_THRESHOLD
    ) or (p95 is not None and rainfall_3d_mm >= EXTREME_P95_MULTIPLIER * p95)

    return {
        "asset_id": asset_id,
        "station_id": station_id,
        "as_of_date": as_of_date,
        "rainfall_1d_mm": trailing["rainfall_1d_mm"],
        "rainfall_3d_mm": rainfall_3d_mm,
        "rainfall_7d_mm": trailing["rainfall_7d_mm"],
        "rainfall_30d_mm": trailing["rainfall_30d_mm"],
        "rainfall_p95_station": stats["rainfall_p95_station"],
        "rainfall_p99_station": stats["rainfall_p99_station"],
        "rainfall_percentile": rainfall_percentile,
        "max_365d_rainfall_mm": stats["max_365d_rainfall_mm"],
        "days_above_p95_365d": stats["days_above_p95_365d"],
        "extreme_rainfall_flag": bool(extreme),
    }


_BASE_SQL = """
SELECT
    a.asset_id AS asset_id,
    asm.station_id AS station_id,
    o.observation_date AS observation_date,
    o.rainfall_mm AS rainfall_mm,
    a.postcode AS postcode,
    a.lga_code AS lga_code,
    s.station_name AS station_name,
    asm.station_distance_km AS station_distance_km,
    asm.station_confidence_weight AS station_confidence_weight
FROM assets a
JOIN asset_station_mapping asm ON asm.asset_id = a.asset_id
JOIN rainfall_stations s ON s.station_id = asm.station_id
LEFT JOIN rainfall_observations o
    ON o.station_id = asm.station_id
    AND o.observation_date BETWEEN :lookback_start AND :as_of_date
{asset_filter}
ORDER BY a.asset_id, o.observation_date
""".strip()


def build_asset_rainfall_feature_query(
    asset_ids: Sequence[str] | None = None,
    as_of_date: date | None = None,
) -> tuple[TextClause, dict[str, Any]]:
    """Return ``(text_clause, params)`` for the asset-station-observations join.

    Asset IDs flow via an expanding bind parameter; ``as_of_date`` and the
    derived ``lookback_start`` flow as scalar bind parameters. No raw user
    input is interpolated into SQL text.
    """
    effective_as_of = as_of_date or DEFAULT_AS_OF_DATE
    lookback_start = effective_as_of - timedelta(days=LOOKBACK_DAYS - 1)

    params: dict[str, Any] = {
        "as_of_date": effective_as_of,
        "lookback_start": lookback_start,
    }

    asset_filter = ""
    if asset_ids is not None:
        asset_filter = "WHERE a.asset_id IN :asset_ids"
        params["asset_ids"] = list(asset_ids)

    sql = _BASE_SQL.format(asset_filter=asset_filter)
    stmt = text(sql)
    if "asset_ids" in params:
        stmt = stmt.bindparams(bindparam("asset_ids", expanding=True))
    return stmt, params


def fetch_asset_station_observations_for_features(
    db: Session,
    asset_ids: Sequence[str] | None = None,
    as_of_date: date | None = None,
) -> dict[str, dict[str, Any]]:
    """Return per-asset bundles: ``{asset_id: {station_id, observations: [...]}}``.

    Mapped assets always appear in the result, even if they have zero
    observations in the lookback window (LEFT JOIN preserves them).
    """
    stmt, params = build_asset_rainfall_feature_query(asset_ids, as_of_date)
    result = db.execute(stmt, params)
    by_asset: dict[str, dict[str, Any]] = {}
    for row in result:
        m = row._mapping
        asset_id = str(m["asset_id"])
        if asset_id not in by_asset:
            by_asset[asset_id] = {
                "station_id": str(m["station_id"]),
                "observations": [],
            }
        if m["observation_date"] is not None and m["rainfall_mm"] is not None:
            by_asset[asset_id]["observations"].append(
                {
                    "observation_date": m["observation_date"],
                    "rainfall_mm": float(m["rainfall_mm"]),
                }
            )
    return by_asset


def generate_rainfall_feature_records(
    db: Session,
    asset_ids: Sequence[str] | None = None,
    as_of_date: date | None = None,
) -> list[dict[str, Any]]:
    """Generate one feature record per mapped asset with observations."""
    effective_as_of = as_of_date or DEFAULT_AS_OF_DATE
    bundles = fetch_asset_station_observations_for_features(db, asset_ids, effective_as_of)
    out: list[dict[str, Any]] = []
    for asset_id, bundle in bundles.items():
        if not bundle["observations"]:
            continue
        record = calculate_asset_rainfall_feature_record(
            asset_id=asset_id,
            station_id=bundle["station_id"],
            observations=bundle["observations"],
            as_of_date=effective_as_of,
        )
        out.append(record)
    return out


def validate_rainfall_feature_records(
    records: Iterable[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Validate every record + uniqueness on ``(asset_id, as_of_date)``."""
    seen: set[tuple[str, date]] = set()
    out: list[dict[str, Any]] = []
    for record in records:
        validated = RainfallFeatureRecord.model_validate(record)
        key = (validated.asset_id, validated.as_of_date)
        if key in seen:
            raise ValueError(
                f"Duplicate (asset_id, as_of_date) in feature batch: {key}"
            )
        seen.add(key)
        out.append(validated.model_dump())
    return out


def persist_rainfall_features(
    records: Sequence[dict[str, Any]],
    db: Session,
    replace_existing: bool = True,
) -> int:
    """Insert feature rows; replace or skip duplicates by `(asset_id, as_of_date)`."""
    if not records:
        return 0

    validated = validate_rainfall_feature_records(records)
    pairs = [(r["asset_id"], r["as_of_date"]) for r in validated]

    try:
        if replace_existing:
            db.execute(
                delete(RainfallFeature).where(
                    tuple_(
                        RainfallFeature.asset_id,
                        RainfallFeature.as_of_date,
                    ).in_(pairs)
                )
            )
            to_insert = validated
        else:
            existing_rows = db.execute(
                select(
                    RainfallFeature.asset_id,
                    RainfallFeature.as_of_date,
                ).where(
                    tuple_(
                        RainfallFeature.asset_id,
                        RainfallFeature.as_of_date,
                    ).in_(pairs)
                )
            ).all()
            existing_keys = {(row[0], row[1]) for row in existing_rows}
            if existing_keys:
                logger.warning(
                    "Skipping %d existing rainfall_features rows", len(existing_keys)
                )
            to_insert = [
                r
                for r in validated
                if (r["asset_id"], r["as_of_date"]) not in existing_keys
            ]

        orm_rows = [
            RainfallFeature(
                asset_id=r["asset_id"],
                station_id=r["station_id"],
                as_of_date=r["as_of_date"],
                rainfall_1d_mm=r["rainfall_1d_mm"],
                rainfall_3d_mm=r["rainfall_3d_mm"],
                rainfall_7d_mm=r["rainfall_7d_mm"],
                rainfall_30d_mm=r["rainfall_30d_mm"],
                rainfall_p95_station=r["rainfall_p95_station"],
                rainfall_p99_station=r["rainfall_p99_station"],
                rainfall_percentile=r["rainfall_percentile"],
                max_365d_rainfall_mm=r["max_365d_rainfall_mm"],
                days_above_p95_365d=r["days_above_p95_365d"],
                extreme_rainfall_flag=r["extreme_rainfall_flag"],
            )
            for r in to_insert
        ]
        if orm_rows:
            db.add_all(orm_rows)
        db.commit()
        return len(orm_rows)
    except Exception:
        db.rollback()
        raise


def run_rainfall_feature_generation(
    db: Session,
    asset_ids: Sequence[str] | None = None,
    as_of_date: date | None = None,
    replace_existing: bool = True,
) -> dict[str, Any]:
    """Run the rainfall feature pipeline and return a structured summary."""
    effective_as_of = as_of_date or DEFAULT_AS_OF_DATE
    lookback_start = effective_as_of - timedelta(days=LOOKBACK_DAYS - 1)

    n_assets = db.execute(select(func.count()).select_from(Asset)).scalar() or 0
    n_mappings = (
        db.execute(select(func.count()).select_from(AssetStationMapping)).scalar() or 0
    )

    if n_assets == 0:
        raise ValueError("No assets in database; cannot run rainfall feature generation")
    if n_mappings == 0:
        raise ValueError(
            "No asset_station_mapping rows; run match-stations before "
            "feature generation"
        )

    considered = len(asset_ids) if asset_ids is not None else int(n_assets)

    bundles = fetch_asset_station_observations_for_features(
        db, asset_ids, effective_as_of
    )
    mapped_assets = len(bundles)
    assets_without_obs = sum(1 for b in bundles.values() if not b["observations"])
    stations_used = len({b["station_id"] for b in bundles.values()})

    if mapped_assets == 0:
        raise ValueError(
            "No mapped assets found for feature generation "
            "(check asset_station_mapping coverage and/or asset_ids subset)"
        )
    if all(not b["observations"] for b in bundles.values()):
        raise ValueError(
            f"No rainfall observations available for the lookback window "
            f"{lookback_start}..{effective_as_of}"
        )

    records: list[dict[str, Any]] = []
    for asset_id, bundle in bundles.items():
        if not bundle["observations"]:
            continue
        records.append(
            calculate_asset_rainfall_feature_record(
                asset_id=asset_id,
                station_id=bundle["station_id"],
                observations=bundle["observations"],
                as_of_date=effective_as_of,
            )
        )

    inserted = persist_rainfall_features(records, db, replace_existing)

    extreme_count = sum(1 for r in records if r["extreme_rainfall_flag"])

    summary = {
        "assets_considered": considered,
        "mapped_assets": mapped_assets,
        "stations_used": stations_used,
        "as_of_date": effective_as_of,
        "lookback_start_date": lookback_start,
        "lookback_end_date": effective_as_of,
        "feature_records_generated": len(records),
        "feature_records_inserted": inserted,
        "assets_without_station_mapping": max(0, considered - mapped_assets),
        "assets_without_observations": assets_without_obs,
        "extreme_rainfall_assets": extreme_count,
        "replace_existing": replace_existing,
    }
    RainfallFeatureRunSummary.model_validate(summary)
    return summary


__all__ = [
    "DEFAULT_AS_OF_DATE",
    "EXTREME_P95_MULTIPLIER",
    "EXTREME_PERCENTILE_THRESHOLD",
    "LOOKBACK_DAYS",
    "build_asset_rainfall_feature_query",
    "calculate_asset_rainfall_feature_record",
    "calculate_percentile_rank",
    "calculate_station_daily_statistics",
    "calculate_station_rolling_3d_totals",
    "calculate_trailing_rainfall_totals",
    "fetch_asset_station_observations_for_features",
    "generate_rainfall_feature_records",
    "persist_rainfall_features",
    "run_rainfall_feature_generation",
    "validate_rainfall_feature_records",
]
