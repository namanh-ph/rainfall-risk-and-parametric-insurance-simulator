"""Asset, per-asset risk, rainfall, and station HTTP endpoints.

All handlers are read-only and never trigger ingestion, matching,
feature engineering, scoring, payouts, training, or prediction
"""

from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from src.api.deps import (
    get_db,
    pagination_params,
    parse_as_of_date,
    validate_asset_id,
    validate_risk_band,
)
from src.schemas.api_assets import (
    AssetDetail,
    AssetListItem,
    AssetListResponse,
    AssetRainfallResponse,
    AssetRiskResponse,
    AssetStationResponse,
)
from src.schemas.api_common import PaginationMeta

router = APIRouter(tags=["assets"])

DEFAULT_MODEL_NAME = "rainfall_risk_lgbm"
DEFAULT_MODEL_VERSION = "v1"

_ALLOWED_SORT_FIELDS: dict[str, str] = {
    "asset_id": "a.asset_id",
    "postcode": "a.postcode",
    "industry": "a.industry",
    "asset_value": "a.asset_value",
    "coverage_limit": "a.coverage_limit",
    "risk_score": "ars.risk_score",
    "rainfall_3d_mm": "rf.rainfall_3d_mm",
    "ml_risk_probability": "mp.ml_risk_probability",
    "ml_risk_rank": "mp.ml_risk_rank",
}


def _fetch_asset_list(
    db: Session,
    *,
    limit: int,
    offset: int,
    industry: str | None,
    postcode: str | None,
    lga_code: str | None,
    risk_band: str | None,
    min_risk_score: float | None,
    max_risk_score: float | None,
    as_of_date: date,
    model_name: str,
    model_version: str,
    sort_column: str,
    sort_order: str,
) -> tuple[list[dict[str, Any]], int]:
    """Run the paginated asset-list query and return ``(rows, total)``"""
    params: dict[str, Any] = {
        "as_of_date": as_of_date,
        "model_name": model_name,
        "model_version": model_version,
        "limit": limit,
        "offset": offset,
    }
    where_clauses: list[str] = []
    if industry is not None:
        where_clauses.append("a.industry = :industry")
        params["industry"] = industry
    if postcode is not None:
        where_clauses.append("a.postcode = :postcode")
        params["postcode"] = postcode
    if lga_code is not None:
        where_clauses.append("a.lga_code = :lga_code")
        params["lga_code"] = lga_code
    if risk_band is not None:
        where_clauses.append("ars.risk_band = :risk_band")
        params["risk_band"] = risk_band
    if min_risk_score is not None:
        where_clauses.append("ars.risk_score >= :min_risk_score")
        params["min_risk_score"] = min_risk_score
    if max_risk_score is not None:
        where_clauses.append("ars.risk_score <= :max_risk_score")
        params["max_risk_score"] = max_risk_score
    where_sql = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""

    base_from = """
FROM assets a
LEFT JOIN lga_boundaries l ON l.lga_code = a.lga_code
LEFT JOIN asset_risk_scores ars
    ON ars.asset_id = a.asset_id AND ars.as_of_date = :as_of_date
LEFT JOIN rainfall_features rf
    ON rf.asset_id = a.asset_id AND rf.as_of_date = :as_of_date
LEFT JOIN asset_station_mapping asm ON asm.asset_id = a.asset_id
LEFT JOIN model_predictions mp
    ON mp.asset_id = a.asset_id
    AND mp.as_of_date = :as_of_date
    AND mp.model_name = :model_name
    AND mp.model_version = :model_version
"""

    count_sql = f"SELECT COUNT(*) {base_from} {where_sql}"
    total = db.execute(text(count_sql), params).scalar() or 0

    list_sql = f"""
SELECT
    a.asset_id, a.business_type, a.industry, a.postcode,
    a.latitude, a.longitude,
    a.asset_value, a.annual_revenue, a.coverage_limit,
    a.lga_code, l.lga_name,
    ars.risk_score, ars.risk_band,
    rf.rainfall_3d_mm,
    asm.station_id, asm.station_distance_km,
    mp.ml_risk_probability, mp.ml_risk_rank
{base_from}
{where_sql}
ORDER BY {sort_column} {sort_order}, a.asset_id ASC
LIMIT :limit OFFSET :offset
"""
    result = db.execute(text(list_sql), params)
    rows = [dict(row._mapping) for row in result]
    return rows, int(total)


@router.get("/assets", response_model=AssetListResponse)
def list_assets(
    pagination: dict = Depends(pagination_params),
    industry: str | None = Query(None),
    postcode: str | None = Query(None),
    lga_code: str | None = Query(None),
    risk_band: str | None = Query(None),
    min_risk_score: float | None = Query(None),
    max_risk_score: float | None = Query(None),
    as_of_date: date = Depends(parse_as_of_date),
    sort_by: str = Query("asset_id"),
    sort_order: str = Query("asc"),
    model_name: str = Query(DEFAULT_MODEL_NAME),
    model_version: str = Query(DEFAULT_MODEL_VERSION),
    db: Session = Depends(get_db),
) -> AssetListResponse:
    if sort_by not in _ALLOWED_SORT_FIELDS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"sort_by must be one of {sorted(_ALLOWED_SORT_FIELDS)}",
        )
    if sort_order.lower() not in ("asc", "desc"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="sort_order must be 'asc' or 'desc'",
        )
    validated_risk_band = validate_risk_band(risk_band)

    rows, total = _fetch_asset_list(
        db,
        limit=pagination["limit"],
        offset=pagination["offset"],
        industry=industry,
        postcode=postcode,
        lga_code=lga_code,
        risk_band=validated_risk_band,
        min_risk_score=min_risk_score,
        max_risk_score=max_risk_score,
        as_of_date=as_of_date,
        model_name=model_name,
        model_version=model_version,
        sort_column=_ALLOWED_SORT_FIELDS[sort_by],
        sort_order=sort_order.upper(),
    )

    items = [AssetListItem.model_validate(r) for r in rows]
    return AssetListResponse(
        items=items,
        pagination=PaginationMeta(
            limit=pagination["limit"],
            offset=pagination["offset"],
            total=total,
            returned=len(items),
        ),
    )


def _asset_exists(db: Session, asset_id: str) -> bool:
    row = db.execute(
        text("SELECT 1 FROM assets WHERE asset_id = :asset_id"),
        {"asset_id": asset_id},
    ).first()
    return row is not None


def _fetch_asset_detail(
    db: Session,
    asset_id: str,
    as_of_date: date,
    model_name: str,
    model_version: str,
) -> dict[str, Any] | None:
    sql = text(
        """
SELECT
    a.asset_id, a.business_type, a.industry, a.postcode,
    a.latitude, a.longitude,
    a.asset_value, a.annual_revenue, a.coverage_limit,
    a.lga_code, l.lga_name,
    ars.risk_score, ars.risk_band,
    rf.rainfall_1d_mm, rf.rainfall_3d_mm, rf.rainfall_7d_mm, rf.rainfall_30d_mm,
    rf.rainfall_percentile, rf.extreme_rainfall_flag,
    asm.station_id, s.station_name,
    asm.station_distance_km, asm.station_confidence_weight,
    mp.ml_risk_probability, mp.ml_risk_rank, mp.top_risk_driver
FROM assets a
LEFT JOIN lga_boundaries l ON l.lga_code = a.lga_code
LEFT JOIN asset_risk_scores ars
    ON ars.asset_id = a.asset_id AND ars.as_of_date = :as_of_date
LEFT JOIN rainfall_features rf
    ON rf.asset_id = a.asset_id AND rf.as_of_date = :as_of_date
LEFT JOIN asset_station_mapping asm ON asm.asset_id = a.asset_id
LEFT JOIN rainfall_stations s ON s.station_id = asm.station_id
LEFT JOIN model_predictions mp
    ON mp.asset_id = a.asset_id
    AND mp.as_of_date = :as_of_date
    AND mp.model_name = :model_name
    AND mp.model_version = :model_version
WHERE a.asset_id = :asset_id
"""
    )
    row = db.execute(
        sql,
        {
            "asset_id": asset_id,
            "as_of_date": as_of_date,
            "model_name": model_name,
            "model_version": model_version,
        },
    ).first()
    return dict(row._mapping) if row else None


@router.get("/assets/{asset_id}", response_model=AssetDetail)
def get_asset_detail(
    asset_id: str,
    as_of_date: date = Depends(parse_as_of_date),
    model_name: str = Query(DEFAULT_MODEL_NAME),
    model_version: str = Query(DEFAULT_MODEL_VERSION),
    db: Session = Depends(get_db),
) -> AssetDetail:
    asset_id = validate_asset_id(asset_id)
    row = _fetch_asset_detail(db, asset_id, as_of_date, model_name, model_version)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"asset_id {asset_id!r} not found",
        )
    return AssetDetail.model_validate(row)


def _fetch_asset_risk(
    db: Session, asset_id: str, as_of_date: date
) -> dict[str, Any] | None:
    sql = text(
        """
SELECT
    asset_id, as_of_date,
    rainfall_extreme_score, exposure_weight, vulnerability_weight,
    station_confidence_weight, raw_score, risk_score, risk_band
FROM asset_risk_scores
WHERE asset_id = :asset_id AND as_of_date = :as_of_date
"""
    )
    row = db.execute(sql, {"asset_id": asset_id, "as_of_date": as_of_date}).first()
    return dict(row._mapping) if row else None


@router.get("/assets/{asset_id}/risk", response_model=AssetRiskResponse)
def get_asset_risk(
    asset_id: str,
    as_of_date: date = Depends(parse_as_of_date),
    db: Session = Depends(get_db),
) -> AssetRiskResponse:
    asset_id = validate_asset_id(asset_id)
    if not _asset_exists(db, asset_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"asset_id {asset_id!r} not found",
        )
    row = _fetch_asset_risk(db, asset_id, as_of_date)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"No asset_risk_scores row for asset_id={asset_id!r} "
                f"as_of_date={as_of_date.isoformat()}"
            ),
        )
    return AssetRiskResponse.model_validate(row)


def _fetch_asset_rainfall(
    db: Session, asset_id: str, as_of_date: date
) -> dict[str, Any] | None:
    sql = text(
        """
SELECT
    asset_id, station_id, as_of_date,
    rainfall_1d_mm, rainfall_3d_mm, rainfall_7d_mm, rainfall_30d_mm,
    rainfall_p95_station, rainfall_p99_station, rainfall_percentile,
    max_365d_rainfall_mm, days_above_p95_365d, extreme_rainfall_flag
FROM rainfall_features
WHERE asset_id = :asset_id AND as_of_date = :as_of_date
"""
    )
    row = db.execute(sql, {"asset_id": asset_id, "as_of_date": as_of_date}).first()
    return dict(row._mapping) if row else None


@router.get("/assets/{asset_id}/rainfall", response_model=AssetRainfallResponse)
def get_asset_rainfall(
    asset_id: str,
    as_of_date: date = Depends(parse_as_of_date),
    db: Session = Depends(get_db),
) -> AssetRainfallResponse:
    asset_id = validate_asset_id(asset_id)
    if not _asset_exists(db, asset_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"asset_id {asset_id!r} not found",
        )
    row = _fetch_asset_rainfall(db, asset_id, as_of_date)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"No rainfall_features row for asset_id={asset_id!r} "
                f"as_of_date={as_of_date.isoformat()}"
            ),
        )
    return AssetRainfallResponse.model_validate(row)


def _fetch_asset_station(db: Session, asset_id: str) -> dict[str, Any] | None:
    sql = text(
        """
SELECT
    asm.asset_id, asm.station_id, s.station_name,
    s.latitude, s.longitude,
    asm.station_distance_km, asm.station_confidence_weight,
    asm.matched_at, s.data_source
FROM asset_station_mapping asm
JOIN rainfall_stations s ON s.station_id = asm.station_id
WHERE asm.asset_id = :asset_id
"""
    )
    row = db.execute(sql, {"asset_id": asset_id}).first()
    return dict(row._mapping) if row else None


@router.get("/assets/{asset_id}/station", response_model=AssetStationResponse)
def get_asset_station(
    asset_id: str,
    db: Session = Depends(get_db),
) -> AssetStationResponse:
    asset_id = validate_asset_id(asset_id)
    if not _asset_exists(db, asset_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"asset_id {asset_id!r} not found",
        )
    row = _fetch_asset_station(db, asset_id)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"No station mapping found for asset_id={asset_id!r} "
                f"(check asset_station_mapping and rainfall_stations)"
            ),
        )
    return AssetStationResponse.model_validate(row)


__all__ = ["router"]
