"""Portfolio summary and risk-ranking HTTP endpoints.

Read-only against persisted tables. No ingestion, matching, feature
engineering, scoring, payout, training, or prediction code path is
invoked from a request handler
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
    validate_risk_band,
)
from src.domain.constants import DEFAULT_PAYOUT_SIMULATION_ID
from src.schemas.api_common import PaginationMeta
from src.schemas.api_portfolio import (
    IndustryRiskSummaryItem,
    LgaRiskSummaryItem,
    PortfolioRiskRankingItem,
    PortfolioRiskRankingResponse,
    PortfolioSummaryResponse,
    RiskBandDistributionItem,
)

router = APIRouter(tags=["portfolio"])

DEFAULT_MODEL_NAME = "rainfall_risk_lgbm"
DEFAULT_MODEL_VERSION = "v1"

_PORTFOLIO_BASE_FROM = """
FROM assets a
LEFT JOIN lga_boundaries l ON l.lga_code = a.lga_code
LEFT JOIN asset_risk_scores ars
    ON ars.asset_id = a.asset_id AND ars.as_of_date = :as_of_date
LEFT JOIN rainfall_features rf
    ON rf.asset_id = a.asset_id AND rf.as_of_date = :as_of_date
LEFT JOIN payout_results pr
    ON pr.asset_id = a.asset_id AND pr.simulation_id = :simulation_id
LEFT JOIN model_predictions mp
    ON mp.asset_id = a.asset_id
    AND mp.as_of_date = :as_of_date
    AND mp.model_name = :model_name
    AND mp.model_version = :model_version
"""


def _portfolio_params(
    as_of_date: date,
    simulation_id: str,
    model_name: str,
    model_version: str,
) -> dict[str, Any]:
    return {
        "as_of_date": as_of_date,
        "simulation_id": simulation_id,
        "model_name": model_name,
        "model_version": model_version,
    }


def _fetch_portfolio_totals(
    db: Session,
    as_of_date: date,
    simulation_id: str,
    model_name: str,
    model_version: str,
) -> dict[str, Any]:
    sql = text(
        f"""
SELECT
    COUNT(*) AS total_assets,
    COALESCE(SUM(a.asset_value), 0) AS total_asset_value,
    COALESCE(SUM(a.coverage_limit), 0) AS total_coverage_limit,
    AVG(ars.risk_score) AS average_risk_score,
    COALESCE(COUNT(*) FILTER (WHERE ars.risk_band IN ('High','Severe')), 0)
        AS high_or_severe_assets,
    COALESCE(COUNT(*) FILTER (WHERE pr.trigger_status = 'triggered'), 0)
        AS triggered_assets,
    COALESCE(SUM(pr.estimated_payout), 0) AS total_estimated_payout,
    AVG(mp.ml_risk_probability) AS average_ml_risk_probability
{_PORTFOLIO_BASE_FROM}
"""
    )
    params = _portfolio_params(as_of_date, simulation_id, model_name, model_version)
    row = db.execute(sql, params).first()
    return dict(row._mapping) if row else {}


def _fetch_risk_band_distribution(
    db: Session,
    as_of_date: date,
    simulation_id: str,
) -> list[dict[str, Any]]:
    sql = text(
        """
SELECT
    ars.risk_band AS risk_band,
    COUNT(*) AS asset_count,
    AVG(ars.risk_score) AS average_risk_score,
    COALESCE(SUM(a.coverage_limit), 0) AS total_coverage_limit,
    COALESCE(SUM(pr.estimated_payout), 0) AS total_estimated_payout
FROM assets a
JOIN asset_risk_scores ars
    ON ars.asset_id = a.asset_id AND ars.as_of_date = :as_of_date
LEFT JOIN payout_results pr
    ON pr.asset_id = a.asset_id AND pr.simulation_id = :simulation_id
WHERE ars.risk_band IN ('Low','Medium','High','Severe')
GROUP BY ars.risk_band
ORDER BY
    CASE ars.risk_band
        WHEN 'Low' THEN 1
        WHEN 'Medium' THEN 2
        WHEN 'High' THEN 3
        WHEN 'Severe' THEN 4
    END
"""
    )
    return [
        dict(r._mapping)
        for r in db.execute(
            sql, {"as_of_date": as_of_date, "simulation_id": simulation_id}
        )
    ]


def _fetch_industry_summary(
    db: Session,
    as_of_date: date,
    simulation_id: str,
) -> list[dict[str, Any]]:
    sql = text(
        """
SELECT
    a.industry AS industry,
    COUNT(*) AS asset_count,
    AVG(ars.risk_score) AS average_risk_score,
    COALESCE(COUNT(*) FILTER (WHERE ars.risk_band IN ('High','Severe')), 0)
        AS high_or_severe_assets,
    COALESCE(COUNT(*) FILTER (WHERE pr.trigger_status = 'triggered'), 0)
        AS triggered_assets,
    COALESCE(SUM(a.coverage_limit), 0) AS total_coverage_limit,
    COALESCE(SUM(pr.estimated_payout), 0) AS total_estimated_payout
FROM assets a
LEFT JOIN asset_risk_scores ars
    ON ars.asset_id = a.asset_id AND ars.as_of_date = :as_of_date
LEFT JOIN payout_results pr
    ON pr.asset_id = a.asset_id AND pr.simulation_id = :simulation_id
GROUP BY a.industry
ORDER BY a.industry
"""
    )
    return [
        dict(r._mapping)
        for r in db.execute(
            sql, {"as_of_date": as_of_date, "simulation_id": simulation_id}
        )
    ]


def _fetch_lga_summary(
    db: Session,
    as_of_date: date,
    simulation_id: str,
) -> list[dict[str, Any]]:
    sql = text(
        """
SELECT
    a.lga_code AS lga_code,
    l.lga_name AS lga_name,
    COUNT(*) AS asset_count,
    AVG(ars.risk_score) AS average_risk_score,
    COALESCE(COUNT(*) FILTER (WHERE ars.risk_band IN ('High','Severe')), 0)
        AS high_or_severe_assets,
    COALESCE(COUNT(*) FILTER (WHERE pr.trigger_status = 'triggered'), 0)
        AS triggered_assets,
    COALESCE(SUM(a.coverage_limit), 0) AS total_coverage_limit,
    COALESCE(SUM(pr.estimated_payout), 0) AS total_estimated_payout
FROM assets a
LEFT JOIN lga_boundaries l ON l.lga_code = a.lga_code
LEFT JOIN asset_risk_scores ars
    ON ars.asset_id = a.asset_id AND ars.as_of_date = :as_of_date
LEFT JOIN payout_results pr
    ON pr.asset_id = a.asset_id AND pr.simulation_id = :simulation_id
WHERE a.lga_code IS NOT NULL
GROUP BY a.lga_code, l.lga_name
ORDER BY a.lga_code
"""
    )
    return [
        dict(r._mapping)
        for r in db.execute(
            sql, {"as_of_date": as_of_date, "simulation_id": simulation_id}
        )
    ]


_ALLOWED_RANKING_SORT_FIELDS = {
    "risk_score": "ars.risk_score",
    "ml_risk_probability": "mp.ml_risk_probability",
    "ml_risk_rank": "mp.ml_risk_rank",
    "estimated_payout": "pr.estimated_payout",
    "rainfall_3d_mm": "rf.rainfall_3d_mm",
    "asset_id": "a.asset_id",
    "asset_value": "a.asset_value",
    "coverage_limit": "a.coverage_limit",
}


def _fetch_risk_ranking(
    db: Session,
    *,
    limit: int,
    offset: int,
    as_of_date: date,
    simulation_id: str,
    model_name: str,
    model_version: str,
    risk_band: str | None,
    industry: str | None,
    lga_code: str | None,
    triggered_only: bool,
    sort_column: str,
    sort_order: str,
) -> tuple[list[dict[str, Any]], int]:
    params = _portfolio_params(as_of_date, simulation_id, model_name, model_version)
    params["limit"] = limit
    params["offset"] = offset

    extra_where: list[str] = []
    if risk_band is not None:
        extra_where.append("ars.risk_band = :risk_band")
        params["risk_band"] = risk_band
    if industry is not None:
        extra_where.append("a.industry = :industry")
        params["industry"] = industry
    if lga_code is not None:
        extra_where.append("a.lga_code = :lga_code")
        params["lga_code"] = lga_code
    if triggered_only:
        extra_where.append("pr.trigger_status = 'triggered'")
    extra_where_sql = (" WHERE " + " AND ".join(extra_where)) if extra_where else ""

    count_sql = text(
        f"SELECT COUNT(*) {_PORTFOLIO_BASE_FROM} {extra_where_sql}"
    )
    total = db.execute(count_sql, params).scalar() or 0

    list_sql = text(
        f"""
SELECT
    a.asset_id, a.business_type, a.industry, a.postcode,
    a.lga_code, l.lga_name,
    a.asset_value, a.coverage_limit,
    ars.risk_score, ars.risk_band,
    rf.rainfall_3d_mm, rf.rainfall_percentile, rf.extreme_rainfall_flag,
    pr.trigger_status, pr.estimated_payout,
    mp.ml_risk_probability, mp.ml_risk_rank, mp.top_risk_driver
{_PORTFOLIO_BASE_FROM}
{extra_where_sql}
ORDER BY {sort_column} {sort_order} NULLS LAST, a.asset_id ASC
LIMIT :limit OFFSET :offset
"""
    )
    rows = [dict(r._mapping) for r in db.execute(list_sql, params)]
    return rows, int(total)


@router.get("/portfolio/summary", response_model=PortfolioSummaryResponse)
def portfolio_summary(
    as_of_date: date = Depends(parse_as_of_date),
    simulation_id: str = Query(DEFAULT_PAYOUT_SIMULATION_ID),
    model_name: str = Query(DEFAULT_MODEL_NAME),
    model_version: str = Query(DEFAULT_MODEL_VERSION),
    db: Session = Depends(get_db),
) -> PortfolioSummaryResponse:
    totals = _fetch_portfolio_totals(
        db, as_of_date, simulation_id, model_name, model_version
    )
    bands = _fetch_risk_band_distribution(db, as_of_date, simulation_id)
    industries = _fetch_industry_summary(db, as_of_date, simulation_id)
    lgas = _fetch_lga_summary(db, as_of_date, simulation_id)

    payload: dict[str, Any] = {
        "as_of_date": as_of_date,
        "simulation_id": simulation_id,
        "model_name": model_name,
        "model_version": model_version,
        "total_assets": int(totals.get("total_assets") or 0),
        "total_asset_value": float(totals.get("total_asset_value") or 0.0),
        "total_coverage_limit": float(totals.get("total_coverage_limit") or 0.0),
        "average_risk_score": (
            float(totals["average_risk_score"])
            if totals.get("average_risk_score") is not None
            else None
        ),
        "high_or_severe_assets": int(totals.get("high_or_severe_assets") or 0),
        "triggered_assets": int(totals.get("triggered_assets") or 0),
        "total_estimated_payout": float(totals.get("total_estimated_payout") or 0.0),
        "average_ml_risk_probability": (
            float(totals["average_ml_risk_probability"])
            if totals.get("average_ml_risk_probability") is not None
            else None
        ),
        "risk_band_distribution": [
            RiskBandDistributionItem.model_validate(row) for row in bands
        ],
        "industry_summary": [
            IndustryRiskSummaryItem.model_validate(row) for row in industries
        ],
        "lga_summary": [LgaRiskSummaryItem.model_validate(row) for row in lgas],
    }
    return PortfolioSummaryResponse.model_validate(payload)


@router.get("/portfolio/risk-ranking", response_model=PortfolioRiskRankingResponse)
def portfolio_risk_ranking(
    pagination: dict = Depends(pagination_params),
    as_of_date: date = Depends(parse_as_of_date),
    simulation_id: str = Query(DEFAULT_PAYOUT_SIMULATION_ID),
    model_name: str = Query(DEFAULT_MODEL_NAME),
    model_version: str = Query(DEFAULT_MODEL_VERSION),
    risk_band: str | None = Query(None),
    industry: str | None = Query(None),
    lga_code: str | None = Query(None),
    triggered_only: bool = Query(False),
    sort_by: str = Query("risk_score"),
    sort_order: str = Query("desc"),
    db: Session = Depends(get_db),
) -> PortfolioRiskRankingResponse:
    if sort_by not in _ALLOWED_RANKING_SORT_FIELDS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"sort_by must be one of {sorted(_ALLOWED_RANKING_SORT_FIELDS)}",
        )
    if sort_order.lower() not in ("asc", "desc"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="sort_order must be 'asc' or 'desc'",
        )
    validated_band = validate_risk_band(risk_band)

    rows, total = _fetch_risk_ranking(
        db,
        limit=pagination["limit"],
        offset=pagination["offset"],
        as_of_date=as_of_date,
        simulation_id=simulation_id,
        model_name=model_name,
        model_version=model_version,
        risk_band=validated_band,
        industry=industry,
        lga_code=lga_code,
        triggered_only=triggered_only,
        sort_column=_ALLOWED_RANKING_SORT_FIELDS[sort_by],
        sort_order=sort_order.upper(),
    )

    items: list[PortfolioRiskRankingItem] = []
    for i, row in enumerate(rows):
        ranked = {"rank": pagination["offset"] + i + 1, **row}
        items.append(PortfolioRiskRankingItem.model_validate(ranked))

    return PortfolioRiskRankingResponse(
        items=items,
        pagination=PaginationMeta(
            limit=pagination["limit"],
            offset=pagination["offset"],
            total=total,
            returned=len(items),
        ),
        sort_by=sort_by,
        sort_order=sort_order.lower(),
        as_of_date=as_of_date,
        simulation_id=simulation_id,
        model_name=model_name,
        model_version=model_version,
    )


__all__ = ["router"]
