"""ML training dataset construction.

Writes one model_training_data row per (asset_id, as_of_date,
feature_version) by joining assets, asset_station_mapping,
rainfall_features, asset_risk_scores, lga_boundaries, and
payout_results.

The target target_extreme_rainfall_event is derived from rainfall
severity directly, not from payout_results or risk_score, so the
ranker learns rainfall exposure rather than the payout / scoring rules.
"""

from __future__ import annotations

import json
import logging
import math
from collections.abc import Iterable, Sequence
from datetime import date
from typing import Any

from sqlalchemy import bindparam, delete, select, text, tuple_
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import TextClause

from src.db.models import ModelTrainingData
from src.domain.constants import DEFAULT_PAYOUT_SIMULATION_ID, RISK_BANDS
from src.insurance.simulation import build_simulation_id
from src.schemas.ml_dataset import (
    ModelTrainingDataBuildSummary,
    ModelTrainingRecord,
)

logger = logging.getLogger(__name__)

DEFAULT_AS_OF_DATE = date(2025, 12, 31)
DEFAULT_FEATURE_VERSION = "rainfall_risk_features_v1"
UNKNOWN_CATEGORY = "__unknown__"
UNKNOWN_CATEGORY_CODE = 0

CATEGORICAL_FIELDS: tuple[str, ...] = (
    "industry",
    "business_type",
    "postcode",
    "lga_code",
    "risk_band",
)


def safe_log1p(value: float | int | None) -> float | None:
    """Return ``log1p(value)`` for finite non-negative numbers, else None."""
    if value is None:
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(numeric) or numeric < 0:
        return None
    return math.log1p(numeric)


def calculate_ratio(
    numerator: float | int | None,
    denominator: float | int | None,
) -> float | None:
    """Return ``numerator / denominator`` or ``None`` when undefined."""
    if numerator is None or denominator is None:
        return None
    try:
        n = float(numerator)
        d = float(denominator)
    except (TypeError, ValueError):
        return None
    if d == 0 or not math.isfinite(d) or not math.isfinite(n):
        return None
    return n / d


def build_category_encoders(
    rows: Iterable[dict[str, Any]],
) -> dict[str, dict[str, int]]:
    """Deterministic per-field encoders.

    For each field in :data:`CATEGORICAL_FIELDS`, collect distinct values,
    sort them lexicographically, and assign codes ``1..N``. The
    ``__unknown__`` sentinel maps to ``0`` and absorbs missing values or
    categories not seen during build time.
    """
    rows_list = list(rows)
    encoders: dict[str, dict[str, int]] = {}
    for field in CATEGORICAL_FIELDS:
        seen: set[str] = set()
        for row in rows_list:
            value = row.get(field)
            if value is None:
                continue
            text_value = str(value).strip()
            if not text_value:
                continue
            seen.add(text_value)
        encoder: dict[str, int] = {UNKNOWN_CATEGORY: UNKNOWN_CATEGORY_CODE}
        for i, value in enumerate(sorted(seen), start=1):
            encoder[value] = i
        encoders[field] = encoder
    return encoders


def encode_category(value: str | None, encoder: dict[str, int]) -> int:
    """Map a category value to its code; unknown values fall back to 0."""
    if value is None:
        return encoder.get(UNKNOWN_CATEGORY, UNKNOWN_CATEGORY_CODE)
    text_value = str(value).strip()
    if not text_value:
        return encoder.get(UNKNOWN_CATEGORY, UNKNOWN_CATEGORY_CODE)
    return encoder.get(text_value, encoder.get(UNKNOWN_CATEGORY, UNKNOWN_CATEGORY_CODE))


def derive_target_extreme_rainfall_event(row: dict[str, Any]) -> bool:
    """Return the binary target for one input row.

    Truth conditions (any one is sufficient):
      - ``extreme_rainfall_flag`` is True
      - ``rainfall_percentile >= 0.95``
      - ``rainfall_3d_mm >= 3 * rainfall_p95_station`` (when p95 > 0)

    Robust to missing values: ``False`` whenever no condition fires.
    """
    if row.get("extreme_rainfall_flag") is True:
        return True

    percentile = row.get("rainfall_percentile")
    if percentile is not None:
        try:
            if float(percentile) >= 0.95:
                return True
        except (TypeError, ValueError):
            pass

    rainfall_3d = row.get("rainfall_3d_mm")
    p95 = row.get("rainfall_p95_station")
    if rainfall_3d is not None and p95 is not None:
        try:
            r3d = float(rainfall_3d)
            p95_value = float(p95)
            if p95_value > 0 and r3d >= 3.0 * p95_value:
                return True
        except (TypeError, ValueError):
            pass

    return False


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(result):
        return None
    return result


def _to_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _to_str(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)


def build_engineered_feature_payload(
    row: dict[str, Any],
    encoders: dict[str, dict[str, int]],
) -> dict[str, Any]:
    """Construct the JSON-serialisable feature payload for one input row."""
    asset_value = _to_float(row.get("asset_value"))
    coverage_limit = _to_float(row.get("coverage_limit"))
    annual_revenue = _to_float(row.get("annual_revenue"))

    rainfall_3d = _to_float(row.get("rainfall_3d_mm"))
    rainfall_30d = _to_float(row.get("rainfall_30d_mm"))
    p95 = _to_float(row.get("rainfall_p95_station"))
    p99 = _to_float(row.get("rainfall_p99_station"))

    risk_band = _to_str(row.get("risk_band"))

    baseline_payout_rate = _to_float(row.get("baseline_payout_rate"))
    baseline_triggered_flag = (
        baseline_payout_rate is not None and baseline_payout_rate > 0
    )

    sensitive_rate = _to_float(row.get("sensitive_threshold_payout_rate"))
    very_sensitive_rate = _to_float(row.get("very_sensitive_threshold_payout_rate"))
    sensitive_payout = _to_float(row.get("sensitive_threshold_estimated_payout"))
    very_sensitive_payout = _to_float(row.get("very_sensitive_threshold_estimated_payout"))

    sensitivity_rates = [r for r in (baseline_payout_rate, sensitive_rate, very_sensitive_rate) if r is not None]
    sensitivity_payouts = [
        p for p in (
            _to_float(row.get("baseline_estimated_payout")),
            sensitive_payout,
            very_sensitive_payout,
        )
        if p is not None
    ]

    payload: dict[str, Any] = {
        "asset_value": asset_value,
        "coverage_limit": coverage_limit,
        "annual_revenue": annual_revenue,
        "log_asset_value": safe_log1p(asset_value),
        "log_coverage_limit": safe_log1p(coverage_limit),
        "log_annual_revenue": safe_log1p(annual_revenue),
        "coverage_to_asset_value_ratio": calculate_ratio(coverage_limit, asset_value),
        "coverage_to_revenue_ratio": calculate_ratio(coverage_limit, annual_revenue),
        "industry": _to_str(row.get("industry")),
        "business_type": _to_str(row.get("business_type")),
        "postcode": _to_str(row.get("postcode")),
        "lga_code": _to_str(row.get("lga_code")),
        "lga_name": _to_str(row.get("lga_name")),
        "industry_code": encode_category(_to_str(row.get("industry")), encoders["industry"]),
        "business_type_code": encode_category(
            _to_str(row.get("business_type")), encoders["business_type"]
        ),
        "postcode_code": encode_category(_to_str(row.get("postcode")), encoders["postcode"]),
        "lga_code_encoded": encode_category(
            _to_str(row.get("lga_code")), encoders["lga_code"]
        ),
        "latitude": _to_float(row.get("latitude")),
        "longitude": _to_float(row.get("longitude")),
        "station_id": _to_str(row.get("station_id")),
        "station_distance_km": _to_float(row.get("station_distance_km")),
        "station_confidence_weight": _to_float(row.get("station_confidence_weight")),
        "has_lga_assignment": row.get("lga_code") is not None,
        "rainfall_1d_mm": _to_float(row.get("rainfall_1d_mm")),
        "rainfall_3d_mm": rainfall_3d,
        "rainfall_7d_mm": _to_float(row.get("rainfall_7d_mm")),
        "rainfall_30d_mm": rainfall_30d,
        "rainfall_p95_station": p95,
        "rainfall_p99_station": p99,
        "rainfall_percentile": _to_float(row.get("rainfall_percentile")),
        "max_365d_rainfall_mm": _to_float(row.get("max_365d_rainfall_mm")),
        "days_above_p95_365d": _to_int(row.get("days_above_p95_365d")),
        "extreme_rainfall_flag": bool(row.get("extreme_rainfall_flag")),
        "rainfall_3d_to_p95_ratio": calculate_ratio(rainfall_3d, p95),
        "rainfall_3d_to_p99_ratio": calculate_ratio(rainfall_3d, p99),
        "rainfall_30d_to_p95_ratio": calculate_ratio(rainfall_30d, p95),
        "rainfall_extreme_score": _to_float(row.get("rainfall_extreme_score")),
        "exposure_weight": _to_float(row.get("exposure_weight")),
        "vulnerability_weight": _to_float(row.get("vulnerability_weight")),
        "raw_score": _to_float(row.get("raw_score")),
        "risk_score": _to_float(row.get("risk_score")),
        "risk_band": risk_band,
        "risk_band_code": encode_category(risk_band, encoders["risk_band"]),
        "baseline_payout_rate": baseline_payout_rate,
        "baseline_trigger_status": _to_str(row.get("baseline_trigger_status")),
        "baseline_estimated_payout": _to_float(row.get("baseline_estimated_payout")),
        "baseline_triggered_flag": baseline_triggered_flag,
        "sensitive_threshold_triggered_flag": (
            sensitive_rate is not None and sensitive_rate > 0
        ),
        "very_sensitive_threshold_triggered_flag": (
            very_sensitive_rate is not None and very_sensitive_rate > 0
        ),
        "max_sensitivity_payout_rate": max(sensitivity_rates) if sensitivity_rates else None,
        "max_sensitivity_estimated_payout": (
            max(sensitivity_payouts) if sensitivity_payouts else None
        ),
    }
    return payload


def build_model_training_record(
    row: dict[str, Any],
    encoders: dict[str, dict[str, int]],
    feature_version: str = DEFAULT_FEATURE_VERSION,
) -> dict[str, Any]:
    """Build the ``model_training_data`` record for one input row."""
    payload = build_engineered_feature_payload(row, encoders)
    target = derive_target_extreme_rainfall_event(row)
    return {
        "asset_id": str(row["asset_id"]),
        "as_of_date": row["as_of_date"],
        "feature_version": str(feature_version),
        "target_extreme_rainfall_event": bool(target),
        "engineered_features_json": payload,
    }


_BASE_SQL = """
SELECT
    a.asset_id AS asset_id,
    rf.as_of_date AS as_of_date,
    a.business_type AS business_type,
    a.industry AS industry,
    a.postcode AS postcode,
    a.latitude AS latitude,
    a.longitude AS longitude,
    a.asset_value AS asset_value,
    a.annual_revenue AS annual_revenue,
    a.coverage_limit AS coverage_limit,
    a.lga_code AS lga_code,
    l.lga_name AS lga_name,
    asm.station_id AS station_id,
    asm.station_distance_km AS station_distance_km,
    asm.station_confidence_weight AS station_confidence_weight,
    rf.rainfall_1d_mm AS rainfall_1d_mm,
    rf.rainfall_3d_mm AS rainfall_3d_mm,
    rf.rainfall_7d_mm AS rainfall_7d_mm,
    rf.rainfall_30d_mm AS rainfall_30d_mm,
    rf.rainfall_p95_station AS rainfall_p95_station,
    rf.rainfall_p99_station AS rainfall_p99_station,
    rf.rainfall_percentile AS rainfall_percentile,
    rf.max_365d_rainfall_mm AS max_365d_rainfall_mm,
    rf.days_above_p95_365d AS days_above_p95_365d,
    rf.extreme_rainfall_flag AS extreme_rainfall_flag,
    ars.rainfall_extreme_score AS rainfall_extreme_score,
    ars.exposure_weight AS exposure_weight,
    ars.vulnerability_weight AS vulnerability_weight,
    ars.raw_score AS raw_score,
    ars.risk_score AS risk_score,
    ars.risk_band AS risk_band,
    pr_base.payout_rate AS baseline_payout_rate,
    pr_base.trigger_status AS baseline_trigger_status,
    pr_base.estimated_payout AS baseline_estimated_payout,
    pr_t040.payout_rate AS sensitive_threshold_payout_rate,
    pr_t040.estimated_payout AS sensitive_threshold_estimated_payout,
    pr_t020.payout_rate AS very_sensitive_threshold_payout_rate,
    pr_t020.estimated_payout AS very_sensitive_threshold_estimated_payout
FROM assets a
JOIN asset_station_mapping asm ON asm.asset_id = a.asset_id
JOIN rainfall_features rf
    ON rf.asset_id = a.asset_id
    AND rf.as_of_date = :as_of_date
JOIN asset_risk_scores ars
    ON ars.asset_id = a.asset_id
    AND ars.as_of_date = :as_of_date
LEFT JOIN lga_boundaries l ON l.lga_code = a.lga_code
LEFT JOIN payout_results pr_base
    ON pr_base.asset_id = a.asset_id
    AND pr_base.simulation_id = :baseline_simulation_id
LEFT JOIN payout_results pr_t040
    ON pr_t040.asset_id = a.asset_id
    AND pr_t040.simulation_id = :sensitive_simulation_id
LEFT JOIN payout_results pr_t020
    ON pr_t020.asset_id = a.asset_id
    AND pr_t020.simulation_id = :very_sensitive_simulation_id
{asset_filter}
ORDER BY a.asset_id
""".strip()


def build_model_training_data_query(
    asset_ids: Sequence[str] | None = None,
    as_of_date: date | None = None,
    baseline_simulation_id: str = DEFAULT_PAYOUT_SIMULATION_ID,
) -> tuple[TextClause, dict[str, Any]]:
    """Return ``(text_clause, params)`` for the training-data input join."""
    effective_as_of = as_of_date or DEFAULT_AS_OF_DATE
    sensitive_sim_id = build_simulation_id("SWEEP", effective_as_of, threshold_1_mm=40)
    very_sensitive_sim_id = build_simulation_id(
        "SWEEP", effective_as_of, threshold_1_mm=20
    )

    params: dict[str, Any] = {
        "as_of_date": effective_as_of,
        "baseline_simulation_id": baseline_simulation_id,
        "sensitive_simulation_id": sensitive_sim_id,
        "very_sensitive_simulation_id": very_sensitive_sim_id,
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


def fetch_model_training_inputs(
    db: Session,
    asset_ids: Sequence[str] | None = None,
    as_of_date: date | None = None,
    baseline_simulation_id: str = DEFAULT_PAYOUT_SIMULATION_ID,
) -> list[dict[str, Any]]:
    """Run the join query and normalise rows to plain dicts."""
    stmt, params = build_model_training_data_query(
        asset_ids=asset_ids,
        as_of_date=as_of_date,
        baseline_simulation_id=baseline_simulation_id,
    )
    result = db.execute(stmt, params)
    out: list[dict[str, Any]] = []
    for row in result:
        m = row._mapping
        out.append(dict(m))
    return out


def generate_model_training_records(
    db: Session,
    asset_ids: Sequence[str] | None = None,
    as_of_date: date | None = None,
    feature_version: str = DEFAULT_FEATURE_VERSION,
    baseline_simulation_id: str = DEFAULT_PAYOUT_SIMULATION_ID,
) -> list[dict[str, Any]]:
    """Fetch inputs and build one ``ModelTrainingData`` record per row."""
    rows = fetch_model_training_inputs(
        db,
        asset_ids=asset_ids,
        as_of_date=as_of_date,
        baseline_simulation_id=baseline_simulation_id,
    )
    if not rows:
        return []
    encoders = build_category_encoders(rows)
    return [build_model_training_record(r, encoders, feature_version) for r in rows]


_REQUIRED_PAYLOAD_KEYS: tuple[str, ...] = (
    "asset_value",
    "coverage_limit",
    "industry",
    "industry_code",
    "business_type",
    "business_type_code",
    "station_distance_km",
    "station_confidence_weight",
    "rainfall_3d_mm",
    "rainfall_percentile",
    "rainfall_3d_to_p95_ratio",
    "risk_score",
    "risk_band",
    "risk_band_code",
    "baseline_payout_rate",
    "baseline_triggered_flag",
)


def validate_model_training_records(
    records: Iterable[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Validate every record + uniqueness on ``(asset_id, as_of_date, feature_version)``."""
    seen: set[tuple[str, date, str]] = set()
    out: list[dict[str, Any]] = []
    for record in records:
        validated = ModelTrainingRecord.model_validate(record)
        key = (validated.asset_id, validated.as_of_date, validated.feature_version)
        if key in seen:
            raise ValueError(
                f"Duplicate (asset_id, as_of_date, feature_version) in training batch: {key}"
            )
        seen.add(key)
        payload = validated.engineered_features_json
        missing = [k for k in _REQUIRED_PAYLOAD_KEYS if k not in payload]
        if missing:
            raise ValueError(
                f"engineered_features_json for {validated.asset_id} is missing required keys: {missing}"
            )
        # JSON round-trip ensures the payload is serialisable
        try:
            json.dumps(payload, default=str)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"engineered_features_json for {validated.asset_id} is not JSON-serialisable: {exc}"
            ) from exc
        out.append(validated.model_dump())
    return out


def persist_model_training_data(
    records: Sequence[dict[str, Any]],
    db: Session,
    replace_existing: bool = True,
) -> int:
    """Insert training rows; replace or skip duplicates by the unique triplet."""
    if not records:
        return 0

    validated = validate_model_training_records(records)
    keys = [
        (r["asset_id"], r["as_of_date"], r["feature_version"]) for r in validated
    ]

    try:
        if replace_existing:
            db.execute(
                delete(ModelTrainingData).where(
                    tuple_(
                        ModelTrainingData.asset_id,
                        ModelTrainingData.as_of_date,
                        ModelTrainingData.feature_version,
                    ).in_(keys)
                )
            )
            to_insert = validated
        else:
            existing_rows = db.execute(
                select(
                    ModelTrainingData.asset_id,
                    ModelTrainingData.as_of_date,
                    ModelTrainingData.feature_version,
                ).where(
                    tuple_(
                        ModelTrainingData.asset_id,
                        ModelTrainingData.as_of_date,
                        ModelTrainingData.feature_version,
                    ).in_(keys)
                )
            ).all()
            existing_keys = {(row[0], row[1], row[2]) for row in existing_rows}
            if existing_keys:
                logger.warning(
                    "Skipping %d existing model_training_data rows", len(existing_keys)
                )
            to_insert = [
                r
                for r in validated
                if (r["asset_id"], r["as_of_date"], r["feature_version"])
                not in existing_keys
            ]

        orm_rows = [
            ModelTrainingData(
                asset_id=r["asset_id"],
                as_of_date=r["as_of_date"],
                feature_version=r["feature_version"],
                target_extreme_rainfall_event=r["target_extreme_rainfall_event"],
                engineered_features_json=r["engineered_features_json"],
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


def run_model_training_data_build(
    db: Session,
    asset_ids: Sequence[str] | None = None,
    as_of_date: date | None = None,
    feature_version: str = DEFAULT_FEATURE_VERSION,
    baseline_simulation_id: str = DEFAULT_PAYOUT_SIMULATION_ID,
    replace_existing: bool = True,
) -> dict[str, Any]:
    """Run the training-data construction pipeline + return a structured summary."""
    if not feature_version:
        raise ValueError("feature_version must be non-empty")

    effective_as_of = as_of_date or DEFAULT_AS_OF_DATE
    rows = fetch_model_training_inputs(
        db,
        asset_ids=asset_ids,
        as_of_date=effective_as_of,
        baseline_simulation_id=baseline_simulation_id,
    )
    if not rows:
        raise ValueError(
            "No input rows for model_training_data build; ensure rainfall_features "
            "and asset_risk_scores exist for the chosen as_of_date."
        )

    encoders = build_category_encoders(rows)
    records = [build_model_training_record(r, encoders, feature_version) for r in rows]
    inserted = persist_model_training_data(records, db, replace_existing=replace_existing)

    positives = sum(1 for r in records if r["target_extreme_rainfall_event"])
    negatives = len(records) - positives
    payload_key_count = (
        len(records[0]["engineered_features_json"]) if records else 0
    )
    encoder_counts = {
        field: max(0, len(enc) - 1)  # exclude the __unknown__ sentinel
        for field, enc in encoders.items()
    }
    # Ensure all required risk-band labels show up even when absent
    encoder_counts["risk_band"] = max(
        encoder_counts.get("risk_band", 0),
        len({rb for rb in (r.get("risk_band") for r in rows) if rb}),
    )
    _ = RISK_BANDS  # labels are documented; encoder reflects observed values

    summary = {
        "as_of_date": effective_as_of,
        "feature_version": feature_version,
        "baseline_simulation_id": baseline_simulation_id,
        "assets_considered": (
            len(asset_ids) if asset_ids is not None else len(rows)
        ),
        "records_generated": len(records),
        "records_inserted": inserted,
        "positive_targets": positives,
        "negative_targets": negatives,
        "positive_target_rate": (
            round(positives / len(records), 6) if records else 0.0
        ),
        "feature_payload_key_count": payload_key_count,
        "categorical_encoder_counts": encoder_counts,
        "replace_existing": replace_existing,
    }
    ModelTrainingDataBuildSummary.model_validate(summary)
    return summary


__all__ = [
    "DEFAULT_AS_OF_DATE",
    "DEFAULT_FEATURE_VERSION",
    "build_category_encoders",
    "build_engineered_feature_payload",
    "build_model_training_data_query",
    "build_model_training_record",
    "calculate_ratio",
    "derive_target_extreme_rainfall_event",
    "encode_category",
    "fetch_model_training_inputs",
    "generate_model_training_records",
    "persist_model_training_data",
    "run_model_training_data_build",
    "safe_log1p",
    "validate_model_training_records",
]
