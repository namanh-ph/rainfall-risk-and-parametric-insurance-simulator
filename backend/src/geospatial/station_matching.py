"""Asset-to-station nearest-neighbour matching.

Distance comes from PostGIS geography(POINT) in metres, divided by 1000.
Confidence weight: max(0.50, 1 - station_distance_km / 100).
"""

from __future__ import annotations

import logging
from collections.abc import Iterable, Sequence
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import bindparam, delete, func, select, text
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import TextClause

from src.db.models import Asset, AssetStationMapping, RainfallStation
from src.domain.constants import (
    STATION_CONFIDENCE_DISTANCE_DIVISOR_KM,
    STATION_CONFIDENCE_FLOOR,
)
from src.schemas.station_matching import StationMatchingRunSummary, StationMatchRecord

logger = logging.getLogger(__name__)


def calculate_station_confidence_weight(station_distance_km: float) -> float:
    """Canonical confidence weight: ``max(0.50, 1 - distance_km / 100)``."""
    if station_distance_km < 0:
        raise ValueError(
            f"station_distance_km must be non-negative (got {station_distance_km})"
        )
    raw = 1.0 - station_distance_km / STATION_CONFIDENCE_DISTANCE_DIVISOR_KM
    return max(STATION_CONFIDENCE_FLOOR, raw)


_BASE_NEAREST_SQL = """
SELECT
    asset.asset_id AS asset_id,
    station.station_id AS station_id,
    ST_Distance(geography(asset.geom), geography(station.geom)) / 1000.0 AS station_distance_km
FROM assets AS asset
JOIN LATERAL (
    SELECT rainfall_stations.station_id, rainfall_stations.geom
    FROM rainfall_stations
    ORDER BY geography(asset.geom) <-> geography(rainfall_stations.geom)
    LIMIT 1
) AS station ON TRUE
""".strip()


def build_nearest_station_query(
    asset_ids: Sequence[str] | None = None,
    max_distance_km: float | None = None,
) -> tuple[TextClause, dict[str, Any]]:
    """Build a parameterised PostGIS nearest-station query.

    Returns ``(text_clause, params)``. The text is never string-formatted
    with user-supplied IDs; ``asset_ids`` flows through an expanding bind
    parameter and ``max_distance_km`` through a scalar bind parameter.
    """
    if max_distance_km is not None and max_distance_km <= 0:
        raise ValueError(
            f"max_distance_km must be positive when provided (got {max_distance_km})"
        )

    sql_parts = [_BASE_NEAREST_SQL]
    params: dict[str, Any] = {}

    if asset_ids is not None:
        sql_parts.append("WHERE asset.asset_id IN :asset_ids")
        params["asset_ids"] = list(asset_ids)

    inner_sql = "\n".join(sql_parts)
    if max_distance_km is not None:
        sql = (
            f"SELECT * FROM (\n{inner_sql}\n) AS m "
            f"WHERE m.station_distance_km <= :max_distance_km"
        )
        params["max_distance_km"] = float(max_distance_km)
    else:
        sql = inner_sql

    stmt = text(sql)
    if "asset_ids" in params:
        stmt = stmt.bindparams(bindparam("asset_ids", expanding=True))
    return stmt, params


def fetch_nearest_station_matches(
    db: Session,
    asset_ids: Sequence[str] | None = None,
    max_distance_km: float | None = None,
) -> list[dict[str, Any]]:
    """Run the nearest-station query and augment each row with confidence + matched_at."""
    stmt, params = build_nearest_station_query(asset_ids, max_distance_km)
    result = db.execute(stmt, params)
    now = datetime.now(UTC)
    out: list[dict[str, Any]] = []
    for row in result:
        # `Row._mapping` is a Mapping[str, Any]; both real SQLAlchemy rows
        # and the test FakeRow expose this attribute uniformly
        mapping = row._mapping
        distance_km = float(mapping["station_distance_km"])
        out.append(
            {
                "asset_id": str(mapping["asset_id"]),
                "station_id": str(mapping["station_id"]),
                "station_distance_km": distance_km,
                "station_confidence_weight": calculate_station_confidence_weight(distance_km),
                "matched_at": now,
            }
        )
    return out


def validate_station_matches(
    matches: Iterable[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Validate every match through ``StationMatchRecord`` + uniqueness."""
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for record in matches:
        validated = StationMatchRecord.model_validate(record)
        if validated.asset_id in seen:
            raise ValueError(
                f"Duplicate asset_id in match batch: {validated.asset_id}"
            )
        seen.add(validated.asset_id)
        out.append(validated.model_dump())
    return out


def replace_asset_station_mappings(
    matches: Sequence[dict[str, Any]],
    db: Session,
    replace_existing: bool = True,
) -> int:
    """Insert station mappings; replace or skip existing per ``replace_existing``."""
    if not matches:
        return 0

    validated = validate_station_matches(matches)
    incoming_ids = [m["asset_id"] for m in validated]

    try:
        if replace_existing:
            db.execute(
                delete(AssetStationMapping).where(
                    AssetStationMapping.asset_id.in_(incoming_ids)
                )
            )
            to_insert = validated
        else:
            existing_rows = db.execute(
                select(AssetStationMapping.asset_id).where(
                    AssetStationMapping.asset_id.in_(incoming_ids)
                )
            ).all()
            existing_ids = {row[0] for row in existing_rows}
            if existing_ids:
                logger.warning(
                    "Skipping %d existing asset_station_mapping rows", len(existing_ids)
                )
            to_insert = [m for m in validated if m["asset_id"] not in existing_ids]

        orm_rows = [
            AssetStationMapping(
                asset_id=m["asset_id"],
                station_id=m["station_id"],
                station_distance_km=m["station_distance_km"],
                station_confidence_weight=m["station_confidence_weight"],
                matched_at=m["matched_at"],
            )
            for m in to_insert
        ]
        if orm_rows:
            db.add_all(orm_rows)
        db.commit()
        return len(orm_rows)
    except Exception:
        db.rollback()
        raise


def run_asset_station_matching(
    db: Session,
    asset_ids: Sequence[str] | None = None,
    max_distance_km: float | None = None,
    replace_existing: bool = True,
) -> dict[str, Any]:
    """Match assets to nearest stations and persist the mappings.

    Returns a structured summary (dict-shaped, validated through
    ``StationMatchingRunSummary``).
    """
    n_assets = db.execute(select(func.count()).select_from(Asset)).scalar() or 0
    n_stations = (
        db.execute(select(func.count()).select_from(RainfallStation)).scalar() or 0
    )

    if n_assets == 0:
        raise ValueError("No assets in database; cannot run station matching")
    if n_stations == 0:
        raise ValueError("No rainfall stations in database; cannot run station matching")

    considered = len(asset_ids) if asset_ids is not None else int(n_assets)

    matches = fetch_nearest_station_matches(db, asset_ids, max_distance_km)
    inserted = replace_asset_station_mappings(matches, db, replace_existing)

    summary = {
        "assets_considered": considered,
        "stations_available": int(n_stations),
        "matches_generated": len(matches),
        "mappings_inserted": inserted,
        "unmatched_assets": max(0, considered - len(matches)),
        "max_distance_km": max_distance_km,
        "replace_existing": replace_existing,
    }
    # Validate the summary shape on the way out so callers get structured errors
    StationMatchingRunSummary.model_validate(summary)
    return summary


__all__ = [
    "build_nearest_station_query",
    "calculate_station_confidence_weight",
    "fetch_nearest_station_matches",
    "replace_asset_station_mappings",
    "run_asset_station_matching",
    "validate_station_matches",
]
