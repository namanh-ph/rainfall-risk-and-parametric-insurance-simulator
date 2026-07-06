"""GeoJSON map endpoints for assets, LGAs, and rainfall stations.

Every endpoint returns an RFC 7946 ``FeatureCollection``. Geometry is
sourced from PostGIS via ``ST_AsGeoJSON`` and parsed back into a Python
dict before the response is serialised; that keeps the wire format
exactly compliant.

The route handlers are read-only and never trigger ingestion, matching,
feature engineering, scoring, payouts, training, or prediction
"""

from __future__ import annotations

import json
import logging
from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

from src.api.deps import (
    get_db,
    map_limit_param,
    parse_as_of_date,
    validate_risk_band,
)
from src.domain.constants import DEFAULT_PAYOUT_SIMULATION_ID
from src.schemas.api_map import GeoJsonFeature, GeoJsonFeatureCollection

logger = logging.getLogger(__name__)
router = APIRouter(tags=["map"])

DEFAULT_MODEL_NAME = "rainfall_risk_lgbm"
DEFAULT_MODEL_VERSION = "v1"


def _parse_geom(raw: str | None) -> dict[str, Any] | None:
    """Parse a PostGIS-produced GeoJSON string into a dict.

    Returns ``None`` if ``raw`` is missing or malformed; the route then
    filters that feature out of the response
    """
    if not raw:
        return None
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError):
        return None
    if not isinstance(parsed, dict) or "type" not in parsed:
        return None
    return parsed


def _fetch_map_assets(
    db: Session,
    *,
    industry: str | None,
    lga_code: str | None,
    risk_band: str | None,
    triggered_only: bool,
    as_of_date: date,
    model_name: str,
    model_version: str,
    baseline_simulation_id: str,
    limit: int,
) -> list[dict[str, Any]]:
    params: dict[str, Any] = {
        "as_of_date": as_of_date,
        "model_name": model_name,
        "model_version": model_version,
        "baseline_simulation_id": baseline_simulation_id,
        "limit": limit,
    }
    where: list[str] = ["a.geom IS NOT NULL"]
    if industry is not None:
        where.append("a.industry = :industry")
        params["industry"] = industry
    if lga_code is not None:
        where.append("a.lga_code = :lga_code")
        params["lga_code"] = lga_code
    if risk_band is not None:
        where.append("ars.risk_band = :risk_band")
        params["risk_band"] = risk_band
    if triggered_only:
        where.append("pr.trigger_status = 'triggered'")

    sql = text(
        f"""
SELECT
    a.asset_id, a.business_type, a.industry, a.postcode,
    a.asset_value, a.coverage_limit,
    a.lga_code, l.lga_name,
    ars.risk_score, ars.risk_band,
    rf.rainfall_3d_mm,
    pr.trigger_status, pr.estimated_payout,
    mp.ml_risk_probability, mp.ml_risk_rank, mp.top_risk_driver,
    asm.station_id, asm.station_distance_km,
    ST_AsGeoJSON(a.geom) AS geom_json
FROM assets a
LEFT JOIN lga_boundaries l ON l.lga_code = a.lga_code
LEFT JOIN asset_risk_scores ars
    ON ars.asset_id = a.asset_id AND ars.as_of_date = :as_of_date
LEFT JOIN rainfall_features rf
    ON rf.asset_id = a.asset_id AND rf.as_of_date = :as_of_date
LEFT JOIN payout_results pr
    ON pr.asset_id = a.asset_id
    AND pr.simulation_id = :baseline_simulation_id
LEFT JOIN asset_station_mapping asm ON asm.asset_id = a.asset_id
LEFT JOIN model_predictions mp
    ON mp.asset_id = a.asset_id
    AND mp.as_of_date = :as_of_date
    AND mp.model_name = :model_name
    AND mp.model_version = :model_version
WHERE {' AND '.join(where)}
ORDER BY a.asset_id
LIMIT :limit
"""
    )
    return [dict(row._mapping) for row in db.execute(sql, params)]


@router.get("/map/assets", response_model=GeoJsonFeatureCollection)
def map_assets(
    industry: str | None = Query(None),
    lga_code: str | None = Query(None),
    risk_band: str | None = Query(None),
    triggered_only: bool = Query(False),
    as_of_date: date = Depends(parse_as_of_date),
    model_name: str = Query(DEFAULT_MODEL_NAME),
    model_version: str = Query(DEFAULT_MODEL_VERSION),
    limit: int = Depends(map_limit_param),
    db: Session = Depends(get_db),
) -> GeoJsonFeatureCollection:
    validated_band = validate_risk_band(risk_band)
    rows = _fetch_map_assets(
        db,
        industry=industry,
        lga_code=lga_code,
        risk_band=validated_band,
        triggered_only=triggered_only,
        as_of_date=as_of_date,
        model_name=model_name,
        model_version=model_version,
        baseline_simulation_id=DEFAULT_PAYOUT_SIMULATION_ID,
        limit=limit,
    )
    features: list[GeoJsonFeature] = []
    for row in rows:
        geometry = _parse_geom(row.get("geom_json"))
        if geometry is None:
            continue
        properties = {
            "asset_id": row.get("asset_id"),
            "business_type": row.get("business_type"),
            "industry": row.get("industry"),
            "postcode": row.get("postcode"),
            "asset_value": float(row["asset_value"]) if row.get("asset_value") is not None else None,
            "coverage_limit": float(row["coverage_limit"]) if row.get("coverage_limit") is not None else None,
            "lga_code": row.get("lga_code"),
            "lga_name": row.get("lga_name"),
            "risk_score": float(row["risk_score"]) if row.get("risk_score") is not None else None,
            "risk_band": row.get("risk_band"),
            "rainfall_3d_mm": float(row["rainfall_3d_mm"]) if row.get("rainfall_3d_mm") is not None else None,
            "trigger_status": row.get("trigger_status"),
            "estimated_payout": float(row["estimated_payout"]) if row.get("estimated_payout") is not None else None,
            "ml_risk_probability": float(row["ml_risk_probability"]) if row.get("ml_risk_probability") is not None else None,
            "ml_risk_rank": int(row["ml_risk_rank"]) if row.get("ml_risk_rank") is not None else None,
            "top_risk_driver": row.get("top_risk_driver"),
            "station_id": row.get("station_id"),
            "station_distance_km": float(row["station_distance_km"]) if row.get("station_distance_km") is not None else None,
        }
        features.append(GeoJsonFeature(geometry=geometry, properties=properties))
    return GeoJsonFeatureCollection(features=features)


def _fetch_map_lgas(
    db: Session,
    *,
    include_asset_counts: bool,
    as_of_date: date,
    baseline_simulation_id: str,
) -> list[dict[str, Any]]:
    if include_asset_counts:
        sql = text(
            """
WITH asset_aggregates AS (
    SELECT
        a.lga_code,
        COUNT(a.asset_id) AS asset_count,
        AVG(ars.risk_score) AS average_risk_score,
        SUM(pr.estimated_payout) AS total_estimated_payout,
        COUNT(*) FILTER (WHERE pr.trigger_status = 'triggered') AS triggered_assets
    FROM assets a
    LEFT JOIN asset_risk_scores ars
        ON ars.asset_id = a.asset_id AND ars.as_of_date = :as_of_date
    LEFT JOIN payout_results pr
        ON pr.asset_id = a.asset_id
        AND pr.simulation_id = :baseline_simulation_id
    WHERE a.lga_code IS NOT NULL
    GROUP BY a.lga_code
)
SELECT
    l.lga_code, l.lga_name, l.state, l.data_source,
    COALESCE(agg.asset_count, 0) AS asset_count,
    agg.average_risk_score,
    COALESCE(agg.total_estimated_payout, 0) AS total_estimated_payout,
    COALESCE(agg.triggered_assets, 0) AS triggered_assets,
    ST_AsGeoJSON(l.geom) AS geom_json
FROM lga_boundaries l
LEFT JOIN asset_aggregates agg ON agg.lga_code = l.lga_code
ORDER BY l.lga_code
"""
        )
        params = {
            "as_of_date": as_of_date,
            "baseline_simulation_id": baseline_simulation_id,
        }
    else:
        sql = text(
            """
SELECT
    l.lga_code, l.lga_name, l.state, l.data_source,
    NULL::int AS asset_count,
    NULL::float AS average_risk_score,
    NULL::float AS total_estimated_payout,
    NULL::int AS triggered_assets,
    ST_AsGeoJSON(l.geom) AS geom_json
FROM lga_boundaries l
ORDER BY l.lga_code
"""
        )
        params = {}
    return [dict(row._mapping) for row in db.execute(sql, params)]


@router.get("/map/lgas", response_model=GeoJsonFeatureCollection)
def map_lgas(
    include_asset_counts: bool = Query(True),
    as_of_date: date = Depends(parse_as_of_date),
    db: Session = Depends(get_db),
) -> GeoJsonFeatureCollection:
    rows = _fetch_map_lgas(
        db,
        include_asset_counts=include_asset_counts,
        as_of_date=as_of_date,
        baseline_simulation_id=DEFAULT_PAYOUT_SIMULATION_ID,
    )
    features: list[GeoJsonFeature] = []
    for row in rows:
        geometry = _parse_geom(row.get("geom_json"))
        if geometry is None:
            continue
        properties: dict[str, Any] = {
            "lga_code": row.get("lga_code"),
            "lga_name": row.get("lga_name"),
            "state": row.get("state"),
            "data_source": row.get("data_source"),
            "asset_count": (
                int(row["asset_count"]) if row.get("asset_count") is not None else None
            ),
            "average_risk_score": (
                float(row["average_risk_score"])
                if row.get("average_risk_score") is not None
                else None
            ),
            "total_estimated_payout": (
                float(row["total_estimated_payout"])
                if row.get("total_estimated_payout") is not None
                else None
            ),
            "triggered_assets": (
                int(row["triggered_assets"])
                if row.get("triggered_assets") is not None
                else None
            ),
        }
        features.append(GeoJsonFeature(geometry=geometry, properties=properties))
    return GeoJsonFeatureCollection(features=features)


def _fetch_map_stations(
    db: Session,
    *,
    include_match_counts: bool,
) -> list[dict[str, Any]]:
    if include_match_counts:
        sql = text(
            """
WITH station_aggregates AS (
    SELECT
        station_id,
        COUNT(*) AS matched_asset_count,
        AVG(station_distance_km) AS average_station_distance_km
    FROM asset_station_mapping
    GROUP BY station_id
)
SELECT
    s.station_id, s.station_name, s.elevation_m, s.data_source,
    COALESCE(agg.matched_asset_count, 0) AS matched_asset_count,
    agg.average_station_distance_km,
    ST_AsGeoJSON(s.geom) AS geom_json
FROM rainfall_stations s
LEFT JOIN station_aggregates agg ON agg.station_id = s.station_id
WHERE s.geom IS NOT NULL
ORDER BY s.station_id
"""
        )
    else:
        sql = text(
            """
SELECT
    s.station_id, s.station_name, s.elevation_m, s.data_source,
    NULL::int AS matched_asset_count,
    NULL::float AS average_station_distance_km,
    ST_AsGeoJSON(s.geom) AS geom_json
FROM rainfall_stations s
WHERE s.geom IS NOT NULL
ORDER BY s.station_id
"""
        )
    return [dict(row._mapping) for row in db.execute(sql, {})]


@router.get("/map/stations", response_model=GeoJsonFeatureCollection)
def map_stations(
    include_match_counts: bool = Query(True),
    db: Session = Depends(get_db),
) -> GeoJsonFeatureCollection:
    rows = _fetch_map_stations(db, include_match_counts=include_match_counts)
    features: list[GeoJsonFeature] = []
    for row in rows:
        geometry = _parse_geom(row.get("geom_json"))
        if geometry is None:
            continue
        properties: dict[str, Any] = {
            "station_id": row.get("station_id"),
            "station_name": row.get("station_name"),
            "elevation_m": (
                float(row["elevation_m"]) if row.get("elevation_m") is not None else None
            ),
            "data_source": row.get("data_source"),
            "matched_asset_count": (
                int(row["matched_asset_count"])
                if row.get("matched_asset_count") is not None
                else None
            ),
            "average_station_distance_km": (
                float(row["average_station_distance_km"])
                if row.get("average_station_distance_km") is not None
                else None
            ),
        }
        features.append(GeoJsonFeature(geometry=geometry, properties=properties))
    return GeoJsonFeatureCollection(features=features)


__all__ = ["router"]
