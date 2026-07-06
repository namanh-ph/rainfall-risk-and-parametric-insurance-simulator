"""Rule-based rainfall risk scoring.

    raw_score = rainfall_extreme_score
              * exposure_weight
              * vulnerability_weight
              * station_confidence_weight
    risk_score = min(100, max(0, raw_score))
"""

from __future__ import annotations

import logging
import math
from collections import Counter
from collections.abc import Iterable, Sequence
from datetime import date
from typing import Any

from sqlalchemy import bindparam, delete, func, select, text, tuple_
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import TextClause

from src.db.models import Asset, AssetRiskScore, AssetStationMapping, RainfallFeature
from src.risk.bands import assign_risk_band
from src.schemas.risk import AssetRiskScoreRecord, AssetRiskScoringRunSummary

logger = logging.getLogger(__name__)

DEFAULT_AS_OF_DATE = date(2025, 12, 31)

EXPOSURE_WEIGHT_MIN = 0.8
EXPOSURE_WEIGHT_MAX = 1.3
VULNERABILITY_WEIGHT_MIN = 0.8
VULNERABILITY_WEIGHT_MAX = 1.4
STATION_CONFIDENCE_WEIGHT_MIN = 0.50
STATION_CONFIDENCE_WEIGHT_MAX = 1.00


_INDUSTRY_VULNERABILITY_BASELINE: dict[str, float] = {
    "hospitality": 1.25,
    "logistics": 1.25,
    "retail": 1.15,
    "healthcare": 1.15,
    "agriculture": 1.25,
    "manufacturing": 1.25,
    "professional_services": 0.90,
    "construction": 1.10,
    "tourism": 1.30,
    "education": 1.00,
    "wholesale_trade": 1.15,
    "automotive": 1.10,
    "food_and_beverage": 1.25,
    "community_services": 1.05,
    "technology": 0.90,
    "property_services": 1.00,
    "transport": 1.25,
    "storage": 1.30,
    "recreation": 1.15,
    "essential_services": 1.20,
}

_BUSINESS_TYPE_MODIFIERS: dict[str, float] = {
    # High-vulnerability building/operating types: +0.05 to +0.10
    "cold_storage": 0.10,
    "refrigerated_storage": 0.10,
    "data_centre_small": 0.10,
    "aged_care_facility": 0.10,
    "caravan_park": 0.08,
    "motel": 0.05,
    "warehouse": 0.05,
    "distribution_centre": 0.05,
    "food_processing": 0.08,
    "grain_storage": 0.08,
    # Lower-vulnerability office types: -0.05
    "office": -0.05,
    "consulting_office": -0.05,
    "accounting_firm": -0.05,
    "legal_practice": -0.05,
    "software_office": -0.05,
}

_NEUTRAL_VULNERABILITY = 1.0


def calculate_rainfall_extreme_score(
    rainfall_3d_mm: float,
    rainfall_percentile: float | None,
    rainfall_p95_station: float | None,
    rainfall_p99_station: float | None,
    extreme_rainfall_flag: bool,
) -> float:
    """Return a 0-100 score driven by station-relative rainfall severity.

    The score is monotonic in ``rainfall_percentile`` for fixed other
    inputs. Boosts based on ``extreme_rainfall_flag`` and on the absolute
    ratio against ``p95``/``p99`` push the score upward when a 3-day
    total dwarfs the station's historical distribution.
    """
    if rainfall_3d_mm < 0:
        raise ValueError(f"rainfall_3d_mm must be non-negative (got {rainfall_3d_mm})")

    if rainfall_percentile is not None:
        if not 0.0 <= rainfall_percentile <= 1.0:
            raise ValueError(
                f"rainfall_percentile must be in [0, 1] (got {rainfall_percentile})"
            )
        base = 100.0 * float(rainfall_percentile)
    elif rainfall_p95_station is not None and rainfall_p95_station > 0:
        # Fallback: scale rainfall_3d_mm against 3 * p95 so values at or
        # above 3 * p95 saturate the base score at 100
        ratio = float(rainfall_3d_mm) / (float(rainfall_p95_station) * 3.0)
        base = 100.0 * min(1.0, max(0.0, ratio))
    else:
        base = 0.0

    score = base

    # Severe ratio boosts (monotonic in absolute severity)
    if (
        rainfall_p99_station is not None
        and rainfall_p99_station > 0
        and rainfall_3d_mm >= rainfall_p99_station * 3.0
    ):
        score = max(score, 99.0)
    if (
        rainfall_p95_station is not None
        and rainfall_p95_station > 0
        and rainfall_3d_mm >= rainfall_p95_station * 3.0
    ):
        score = max(score, 90.0)
    if extreme_rainfall_flag:
        score = max(score, 85.0)

    return float(min(100.0, max(0.0, score)))


def _percentile_rank(value: float, distribution: Sequence[float]) -> float:
    if not distribution:
        return 0.5
    n = len(distribution)
    le = sum(1 for d in distribution if d <= value)
    return le / n


def calculate_exposure_weight(
    asset_value: float,
    coverage_limit: float,
    portfolio_asset_values: Sequence[float] | None = None,
    portfolio_coverage_limits: Sequence[float] | None = None,
) -> float:
    """Return a weight in ``[0.8, 1.3]`` reflecting financial exposure.

    With portfolio context (recommended), the weight is the
    log-percentile-rank of the asset within the portfolio. Without
    context, a bounded log-scale fallback keeps results deterministic.
    """
    if asset_value <= 0:
        raise ValueError(f"asset_value must be positive (got {asset_value})")
    if coverage_limit <= 0:
        raise ValueError(f"coverage_limit must be positive (got {coverage_limit})")
    if coverage_limit > asset_value:
        # Tolerate at the scoring layer; ingestion already enforces this
        logger.warning(
            "coverage_limit (%s) exceeds asset_value (%s) for an asset; "
            "scoring will continue but ingestion should have rejected this row.",
            coverage_limit,
            asset_value,
        )

    if portfolio_asset_values and portfolio_coverage_limits:
        log_pa = [math.log(v) for v in portfolio_asset_values if v > 0]
        log_pc = [math.log(v) for v in portfolio_coverage_limits if v > 0]
        if log_pa and log_pc:
            asset_pct = _percentile_rank(math.log(asset_value), log_pa)
            cov_pct = _percentile_rank(math.log(coverage_limit), log_pc)
            combined = 0.6 * asset_pct + 0.4 * cov_pct
            weight = EXPOSURE_WEIGHT_MIN + combined * (
                EXPOSURE_WEIGHT_MAX - EXPOSURE_WEIGHT_MIN
            )
            return _clip_exposure(weight)

    # Bounded log-scale fallback. asset_value of 1e5 -> 0; 1e7+ -> 1
    score_av = max(0.0, min(1.0, (math.log10(asset_value) - 5.0) / 2.5))
    score_cl = max(0.0, min(1.0, (math.log10(coverage_limit) - 4.0) / 2.5))
    combined = 0.6 * score_av + 0.4 * score_cl
    weight = EXPOSURE_WEIGHT_MIN + combined * (
        EXPOSURE_WEIGHT_MAX - EXPOSURE_WEIGHT_MIN
    )
    return _clip_exposure(weight)


def _clip_exposure(value: float) -> float:
    return float(max(EXPOSURE_WEIGHT_MIN, min(EXPOSURE_WEIGHT_MAX, value)))


def calculate_vulnerability_weight(
    industry: str,
    business_type: str | None = None,
) -> float:
    """Return a weight in ``[0.8, 1.4]`` from industry + business-type lookups."""
    if not industry:
        baseline = _NEUTRAL_VULNERABILITY
    else:
        baseline = _INDUSTRY_VULNERABILITY_BASELINE.get(
            industry.lower(), _NEUTRAL_VULNERABILITY
        )
    modifier = 0.0
    if business_type:
        modifier = _BUSINESS_TYPE_MODIFIERS.get(business_type.lower(), 0.0)
    weight = baseline + modifier
    return float(
        max(VULNERABILITY_WEIGHT_MIN, min(VULNERABILITY_WEIGHT_MAX, weight))
    )


def calculate_raw_risk_score(
    rainfall_extreme_score: float,
    exposure_weight: float,
    vulnerability_weight: float,
    station_confidence_weight: float,
) -> float:
    """Canonical multiplicative combination - exact formula."""
    return float(
        rainfall_extreme_score
        * exposure_weight
        * vulnerability_weight
        * station_confidence_weight
    )


def clip_risk_score(raw_score: float) -> float:
    """Clip raw score to ``[0, 100]``."""
    return float(min(100.0, max(0.0, raw_score)))


def calculate_asset_risk_score_record(
    asset_record: dict[str, Any],
    rainfall_feature_record: dict[str, Any],
    station_mapping_record: dict[str, Any],
    portfolio_asset_values: Sequence[float] | None = None,
    portfolio_coverage_limits: Sequence[float] | None = None,
) -> dict[str, Any]:
    """Build the asset_risk_scores record for a single asset."""
    extreme_score = calculate_rainfall_extreme_score(
        rainfall_3d_mm=float(rainfall_feature_record["rainfall_3d_mm"]),
        rainfall_percentile=(
            float(rainfall_feature_record["rainfall_percentile"])
            if rainfall_feature_record.get("rainfall_percentile") is not None
            else None
        ),
        rainfall_p95_station=(
            float(rainfall_feature_record["rainfall_p95_station"])
            if rainfall_feature_record.get("rainfall_p95_station") is not None
            else None
        ),
        rainfall_p99_station=(
            float(rainfall_feature_record["rainfall_p99_station"])
            if rainfall_feature_record.get("rainfall_p99_station") is not None
            else None
        ),
        extreme_rainfall_flag=bool(rainfall_feature_record.get("extreme_rainfall_flag")),
    )
    exposure = calculate_exposure_weight(
        asset_value=float(asset_record["asset_value"]),
        coverage_limit=float(asset_record["coverage_limit"]),
        portfolio_asset_values=portfolio_asset_values,
        portfolio_coverage_limits=portfolio_coverage_limits,
    )
    vulnerability = calculate_vulnerability_weight(
        industry=str(asset_record.get("industry", "")),
        business_type=(
            str(asset_record["business_type"]) if asset_record.get("business_type") else None
        ),
    )
    confidence = float(station_mapping_record["station_confidence_weight"])
    if not (
        STATION_CONFIDENCE_WEIGHT_MIN <= confidence <= STATION_CONFIDENCE_WEIGHT_MAX
    ):
        raise ValueError(
            f"station_confidence_weight must be in "
            f"[{STATION_CONFIDENCE_WEIGHT_MIN}, {STATION_CONFIDENCE_WEIGHT_MAX}] "
            f"(got {confidence})"
        )

    raw = calculate_raw_risk_score(extreme_score, exposure, vulnerability, confidence)
    risk_score = clip_risk_score(raw)
    band = assign_risk_band(risk_score)

    return {
        "asset_id": asset_record["asset_id"],
        "as_of_date": rainfall_feature_record["as_of_date"],
        "rainfall_extreme_score": round(extreme_score, 4),
        "exposure_weight": round(exposure, 4),
        "vulnerability_weight": round(vulnerability, 4),
        "station_confidence_weight": round(confidence, 4),
        "raw_score": round(raw, 4),
        "risk_score": round(risk_score, 2),
        "risk_band": band,
    }


_BASE_SQL = """
SELECT
    a.asset_id AS asset_id,
    a.business_type AS business_type,
    a.industry AS industry,
    a.postcode AS postcode,
    a.lga_code AS lga_code,
    a.asset_value AS asset_value,
    a.coverage_limit AS coverage_limit,
    rf.as_of_date AS as_of_date,
    rf.rainfall_3d_mm AS rainfall_3d_mm,
    rf.rainfall_p95_station AS rainfall_p95_station,
    rf.rainfall_p99_station AS rainfall_p99_station,
    rf.rainfall_percentile AS rainfall_percentile,
    rf.extreme_rainfall_flag AS extreme_rainfall_flag,
    asm.station_id AS station_id,
    asm.station_distance_km AS station_distance_km,
    asm.station_confidence_weight AS station_confidence_weight
FROM assets a
JOIN rainfall_features rf
    ON rf.asset_id = a.asset_id
    AND rf.as_of_date = :as_of_date
JOIN asset_station_mapping asm ON asm.asset_id = a.asset_id
{asset_filter}
ORDER BY a.asset_id
""".strip()


def build_asset_risk_scoring_query(
    asset_ids: Sequence[str] | None = None,
    as_of_date: date | None = None,
) -> tuple[TextClause, dict[str, Any]]:
    """Return ``(text_clause, params)`` for the risk-scoring input join."""
    effective_as_of = as_of_date or DEFAULT_AS_OF_DATE
    params: dict[str, Any] = {"as_of_date": effective_as_of}

    asset_filter = ""
    if asset_ids is not None:
        asset_filter = "WHERE a.asset_id IN :asset_ids"
        params["asset_ids"] = list(asset_ids)

    sql = _BASE_SQL.format(asset_filter=asset_filter)
    stmt = text(sql)
    if "asset_ids" in params:
        stmt = stmt.bindparams(bindparam("asset_ids", expanding=True))
    return stmt, params


def fetch_asset_risk_scoring_inputs(
    db: Session,
    asset_ids: Sequence[str] | None = None,
    as_of_date: date | None = None,
) -> list[dict[str, Any]]:
    """Run the join query and return one input row per matched asset."""
    stmt, params = build_asset_risk_scoring_query(asset_ids, as_of_date)
    result = db.execute(stmt, params)
    out: list[dict[str, Any]] = []
    for row in result:
        m = row._mapping
        out.append(
            {
                "asset_id": str(m["asset_id"]),
                "business_type": m["business_type"],
                "industry": m["industry"],
                "postcode": m["postcode"],
                "lga_code": m["lga_code"],
                "asset_value": float(m["asset_value"]) if m["asset_value"] is not None else None,
                "coverage_limit": float(m["coverage_limit"]) if m["coverage_limit"] is not None else None,
                "as_of_date": m["as_of_date"],
                "rainfall_3d_mm": float(m["rainfall_3d_mm"]) if m["rainfall_3d_mm"] is not None else None,
                "rainfall_p95_station": (
                    float(m["rainfall_p95_station"])
                    if m["rainfall_p95_station"] is not None
                    else None
                ),
                "rainfall_p99_station": (
                    float(m["rainfall_p99_station"])
                    if m["rainfall_p99_station"] is not None
                    else None
                ),
                "rainfall_percentile": (
                    float(m["rainfall_percentile"])
                    if m["rainfall_percentile"] is not None
                    else None
                ),
                "extreme_rainfall_flag": bool(m["extreme_rainfall_flag"]),
                "station_id": m["station_id"],
                "station_distance_km": (
                    float(m["station_distance_km"])
                    if m["station_distance_km"] is not None
                    else None
                ),
                "station_confidence_weight": float(m["station_confidence_weight"]),
            }
        )
    return out


def generate_asset_risk_score_records(
    db: Session,
    asset_ids: Sequence[str] | None = None,
    as_of_date: date | None = None,
) -> list[dict[str, Any]]:
    """Generate one risk-score record per matched asset."""
    rows = fetch_asset_risk_scoring_inputs(db, asset_ids, as_of_date)
    if not rows:
        return []

    portfolio_asset_values = [
        r["asset_value"] for r in rows if r.get("asset_value") and r["asset_value"] > 0
    ]
    portfolio_coverage_limits = [
        r["coverage_limit"]
        for r in rows
        if r.get("coverage_limit") and r["coverage_limit"] > 0
    ]

    out: list[dict[str, Any]] = []
    for r in rows:
        record = calculate_asset_risk_score_record(
            asset_record={
                "asset_id": r["asset_id"],
                "business_type": r["business_type"],
                "industry": r["industry"],
                "asset_value": r["asset_value"],
                "coverage_limit": r["coverage_limit"],
            },
            rainfall_feature_record={
                "as_of_date": r["as_of_date"],
                "rainfall_3d_mm": r["rainfall_3d_mm"],
                "rainfall_p95_station": r["rainfall_p95_station"],
                "rainfall_p99_station": r["rainfall_p99_station"],
                "rainfall_percentile": r["rainfall_percentile"],
                "extreme_rainfall_flag": r["extreme_rainfall_flag"],
            },
            station_mapping_record={
                "station_confidence_weight": r["station_confidence_weight"],
            },
            portfolio_asset_values=portfolio_asset_values,
            portfolio_coverage_limits=portfolio_coverage_limits,
        )
        out.append(record)
    return out


def validate_asset_risk_score_records(
    records: Iterable[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Validate every record + uniqueness on ``(asset_id, as_of_date)``."""
    seen: set[tuple[str, date]] = set()
    out: list[dict[str, Any]] = []
    for record in records:
        validated = AssetRiskScoreRecord.model_validate(record)
        key = (validated.asset_id, validated.as_of_date)
        if key in seen:
            raise ValueError(
                f"Duplicate (asset_id, as_of_date) in risk-score batch: {key}"
            )
        seen.add(key)
        out.append(validated.model_dump())
    return out


def persist_asset_risk_scores(
    records: Sequence[dict[str, Any]],
    db: Session,
    replace_existing: bool = True,
) -> int:
    """Insert risk-score rows; replace or skip duplicates by `(asset_id, as_of_date)`."""
    if not records:
        return 0

    validated = validate_asset_risk_score_records(records)
    pairs = [(r["asset_id"], r["as_of_date"]) for r in validated]

    try:
        if replace_existing:
            db.execute(
                delete(AssetRiskScore).where(
                    tuple_(
                        AssetRiskScore.asset_id,
                        AssetRiskScore.as_of_date,
                    ).in_(pairs)
                )
            )
            to_insert = validated
        else:
            existing_rows = db.execute(
                select(
                    AssetRiskScore.asset_id,
                    AssetRiskScore.as_of_date,
                ).where(
                    tuple_(
                        AssetRiskScore.asset_id,
                        AssetRiskScore.as_of_date,
                    ).in_(pairs)
                )
            ).all()
            existing_keys = {(row[0], row[1]) for row in existing_rows}
            if existing_keys:
                logger.warning(
                    "Skipping %d existing asset_risk_scores rows", len(existing_keys)
                )
            to_insert = [
                r
                for r in validated
                if (r["asset_id"], r["as_of_date"]) not in existing_keys
            ]

        orm_rows = [
            AssetRiskScore(
                asset_id=r["asset_id"],
                as_of_date=r["as_of_date"],
                rainfall_extreme_score=r["rainfall_extreme_score"],
                exposure_weight=r["exposure_weight"],
                vulnerability_weight=r["vulnerability_weight"],
                station_confidence_weight=r["station_confidence_weight"],
                raw_score=r["raw_score"],
                risk_score=r["risk_score"],
                risk_band=r["risk_band"],
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


def run_asset_risk_scoring(
    db: Session,
    asset_ids: Sequence[str] | None = None,
    as_of_date: date | None = None,
    replace_existing: bool = True,
) -> dict[str, Any]:
    """Run the rule-based risk scoring pipeline and return a structured summary."""
    effective_as_of = as_of_date or DEFAULT_AS_OF_DATE

    n_assets = db.execute(select(func.count()).select_from(Asset)).scalar() or 0
    n_features = (
        db.execute(
            select(func.count())
            .select_from(RainfallFeature)
            .where(RainfallFeature.as_of_date == effective_as_of)
        ).scalar()
        or 0
    )
    n_mappings = (
        db.execute(select(func.count()).select_from(AssetStationMapping)).scalar() or 0
    )

    if n_assets == 0:
        raise ValueError("No assets in database; cannot run risk scoring")
    if n_features == 0:
        raise ValueError(
            f"No rainfall_features for as_of_date={effective_as_of}; "
            f"run rainfall feature generation first"
        )
    if n_mappings == 0:
        raise ValueError(
            "No asset_station_mapping rows; run match-stations before risk scoring"
        )

    considered = len(asset_ids) if asset_ids is not None else int(n_assets)
    records = generate_asset_risk_score_records(db, asset_ids, effective_as_of)
    inserted = persist_asset_risk_scores(records, db, replace_existing)

    bands = Counter(r["risk_band"] for r in records)
    avg_score = (
        round(sum(r["risk_score"] for r in records) / len(records), 4)
        if records
        else None
    )

    summary = {
        "assets_considered": considered,
        "feature_records_available": int(n_features),
        "station_mappings_available": int(n_mappings),
        "as_of_date": effective_as_of,
        "risk_score_records_generated": len(records),
        "risk_score_records_inserted": inserted,
        "low_risk_assets": bands.get("Low", 0),
        "medium_risk_assets": bands.get("Medium", 0),
        "high_risk_assets": bands.get("High", 0),
        "severe_risk_assets": bands.get("Severe", 0),
        "average_risk_score": avg_score,
        "replace_existing": replace_existing,
    }
    AssetRiskScoringRunSummary.model_validate(summary)
    return summary


__all__ = [
    "DEFAULT_AS_OF_DATE",
    "EXPOSURE_WEIGHT_MAX",
    "EXPOSURE_WEIGHT_MIN",
    "STATION_CONFIDENCE_WEIGHT_MAX",
    "STATION_CONFIDENCE_WEIGHT_MIN",
    "VULNERABILITY_WEIGHT_MAX",
    "VULNERABILITY_WEIGHT_MIN",
    "build_asset_risk_scoring_query",
    "calculate_asset_risk_score_record",
    "calculate_exposure_weight",
    "calculate_rainfall_extreme_score",
    "calculate_raw_risk_score",
    "calculate_vulnerability_weight",
    "clip_risk_score",
    "fetch_asset_risk_scoring_inputs",
    "generate_asset_risk_score_records",
    "persist_asset_risk_scores",
    "run_asset_risk_scoring",
    "validate_asset_risk_score_records",
]
