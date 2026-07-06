"""Parametric rainfall payout engine.

estimated_payout = coverage_limit * coverage_multiplier * payout_rate.
Trigger input is always rainfall_features.rainfall_3d_mm; risk_score and
risk_band are excluded — the product is parametric, not indemnity.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable, Sequence
from datetime import date
from typing import Any

from sqlalchemy import bindparam, delete, func, select, text, tuple_
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import TextClause

from src.db.models import Asset, PayoutResult, RainfallFeature, SimulationRun
from src.domain.constants import (
    DEFAULT_PAYOUT_COVERAGE_MULTIPLIER,
    DEFAULT_PAYOUT_SIMULATION_ID,
    DEFAULT_PAYOUT_SIMULATION_NAME,
    DEFAULT_PAYOUT_THRESHOLDS,
    TRIGGER_STATUS_NOT_TRIGGERED,
    TRIGGER_STATUS_TRIGGERED,
)
from src.schemas.payout import (
    PayoutResultRecord,
    PayoutSimulationRunSummary,
    PayoutThreshold,
)

logger = logging.getLogger(__name__)

DEFAULT_AS_OF_DATE = date(2025, 12, 31)


def get_default_payout_thresholds() -> list[dict[str, Any]]:
    """Return a deep copy of the payout threshold table."""
    return [dict(t) for t in DEFAULT_PAYOUT_THRESHOLDS]


def validate_payout_thresholds(
    thresholds: Iterable[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Validate a candidate threshold table.

    Rules:
      - every tier passes ``PayoutThreshold`` validation
      - tiers are sorted by ``min_rainfall_3d_mm``
      - tiers do not overlap (each tier's ``max`` <= next tier's ``min``)
      - at most one open-ended tier (``max=None``) and it must be last
    """
    parsed = [PayoutThreshold.model_validate(t) for t in thresholds]
    if not parsed:
        raise ValueError("payout threshold table must not be empty")

    parsed.sort(key=lambda t: t.min_rainfall_3d_mm)
    for i, tier in enumerate(parsed):
        if tier.max_rainfall_3d_mm is None and i != len(parsed) - 1:
            raise ValueError(
                "open-ended tier (max_rainfall_3d_mm=None) must be the last tier"
            )
        if i > 0:
            prev = parsed[i - 1]
            if prev.max_rainfall_3d_mm is None:
                raise ValueError("only the last tier may have max_rainfall_3d_mm=None")
            if tier.min_rainfall_3d_mm < prev.max_rainfall_3d_mm:
                raise ValueError(
                    f"tier {i} min ({tier.min_rainfall_3d_mm}) overlaps previous "
                    f"tier max ({prev.max_rainfall_3d_mm})"
                )
    return [t.model_dump() for t in parsed]


def calculate_payout_rate(
    rainfall_3d_mm: float,
    thresholds: Sequence[dict[str, Any]] | None = None,
) -> float:
    """Return the payout_rate in ``[0, 1]`` for ``rainfall_3d_mm``."""
    if rainfall_3d_mm < 0:
        raise ValueError(f"rainfall_3d_mm must be non-negative (got {rainfall_3d_mm})")

    table = (
        validate_payout_thresholds(thresholds)
        if thresholds is not None
        else get_default_payout_thresholds()
    )
    for tier in table:
        min_mm = float(tier["min_rainfall_3d_mm"])
        max_mm = tier["max_rainfall_3d_mm"]
        if max_mm is None:
            if rainfall_3d_mm >= min_mm:
                return float(tier["payout_rate"])
        elif min_mm <= rainfall_3d_mm < float(max_mm):
            return float(tier["payout_rate"])
    return 0.0


def calculate_trigger_status(payout_rate: float) -> str:
    """Map a payout rate to its trigger-status string."""
    if not 0 <= payout_rate <= 1:
        raise ValueError(f"payout_rate must be in [0, 1] (got {payout_rate})")
    return TRIGGER_STATUS_TRIGGERED if payout_rate > 0 else TRIGGER_STATUS_NOT_TRIGGERED


def calculate_estimated_payout(
    coverage_limit: float,
    payout_rate: float,
    coverage_multiplier: float = 1.0,
) -> float:
    """Return ``coverage_limit * coverage_multiplier * payout_rate`` (non-negative)."""
    if coverage_limit < 0:
        raise ValueError(f"coverage_limit must be non-negative (got {coverage_limit})")
    if not 0 <= payout_rate <= 1:
        raise ValueError(f"payout_rate must be in [0, 1] (got {payout_rate})")
    if coverage_multiplier <= 0:
        raise ValueError(
            f"coverage_multiplier must be positive (got {coverage_multiplier})"
        )
    return float(coverage_limit) * float(coverage_multiplier) * float(payout_rate)


def calculate_asset_payout_record(
    asset_record: dict[str, Any],
    rainfall_feature_record: dict[str, Any],
    risk_score_record: dict[str, Any] | None = None,
    simulation_id: str | None = None,
    thresholds: Sequence[dict[str, Any]] | None = None,
    coverage_multiplier: float = 1.0,
) -> dict[str, Any]:
    """Build the ``payout_results`` record for a single asset."""
    sim_id = simulation_id or DEFAULT_PAYOUT_SIMULATION_ID
    coverage_limit = float(asset_record["coverage_limit"])
    rainfall_3d_mm = float(rainfall_feature_record["rainfall_3d_mm"])

    payout_rate = calculate_payout_rate(rainfall_3d_mm, thresholds)
    estimated_payout = calculate_estimated_payout(
        coverage_limit, payout_rate, coverage_multiplier
    )
    trigger_status = calculate_trigger_status(payout_rate)

    risk_band: str | None = None
    if risk_score_record is not None and risk_score_record.get("risk_band"):
        risk_band = str(risk_score_record["risk_band"])

    return {
        "simulation_id": sim_id,
        "asset_id": asset_record["asset_id"],
        "rainfall_3d_mm": round(rainfall_3d_mm, 4),
        "trigger_status": trigger_status,
        "payout_rate": round(payout_rate, 4),
        "coverage_limit": round(coverage_limit, 2),
        "estimated_payout": round(estimated_payout, 2),
        "risk_band": risk_band,
    }


_SQL_BASE = """
SELECT
    a.asset_id AS asset_id,
    a.coverage_limit AS coverage_limit,
    a.postcode AS postcode,
    a.industry AS industry,
    a.lga_code AS lga_code,
    rf.as_of_date AS as_of_date,
    rf.rainfall_3d_mm AS rainfall_3d_mm{risk_columns}
FROM assets a
JOIN rainfall_features rf
    ON rf.asset_id = a.asset_id
    AND rf.as_of_date = :as_of_date
{risk_join}
{asset_filter}
ORDER BY a.asset_id
""".strip()

_RISK_COLUMNS = ",\n    ars.risk_band AS risk_band,\n    ars.risk_score AS risk_score"
_RISK_JOIN = (
    "LEFT JOIN asset_risk_scores ars\n"
    "    ON ars.asset_id = a.asset_id\n"
    "    AND ars.as_of_date = :as_of_date"
)


def build_payout_input_query(
    asset_ids: Sequence[str] | None = None,
    as_of_date: date | None = None,
    include_risk_band: bool = True,
) -> tuple[TextClause, dict[str, Any]]:
    """Return ``(text_clause, params)`` for the payout-input join."""
    effective_as_of = as_of_date or DEFAULT_AS_OF_DATE
    params: dict[str, Any] = {"as_of_date": effective_as_of}

    risk_columns = _RISK_COLUMNS if include_risk_band else ""
    risk_join = _RISK_JOIN if include_risk_band else ""

    asset_filter = ""
    if asset_ids is not None:
        asset_filter = "WHERE a.asset_id IN :asset_ids"
        params["asset_ids"] = list(asset_ids)

    sql = _SQL_BASE.format(
        risk_columns=risk_columns,
        risk_join=risk_join,
        asset_filter=asset_filter,
    )
    stmt = text(sql)
    if "asset_ids" in params:
        stmt = stmt.bindparams(bindparam("asset_ids", expanding=True))
    return stmt, params


def fetch_payout_inputs(
    db: Session,
    asset_ids: Sequence[str] | None = None,
    as_of_date: date | None = None,
    include_risk_band: bool = True,
) -> list[dict[str, Any]]:
    """Run the payout-input query and return per-asset rows."""
    stmt, params = build_payout_input_query(asset_ids, as_of_date, include_risk_band)
    result = db.execute(stmt, params)
    out: list[dict[str, Any]] = []
    for row in result:
        m = row._mapping
        record: dict[str, Any] = {
            "asset_id": str(m["asset_id"]),
            "coverage_limit": float(m["coverage_limit"]),
            "postcode": m["postcode"],
            "industry": m["industry"],
            "lga_code": m["lga_code"],
            "as_of_date": m["as_of_date"],
            "rainfall_3d_mm": float(m["rainfall_3d_mm"]),
        }
        if include_risk_band:
            record["risk_band"] = m.get("risk_band")
            raw_score = m.get("risk_score")
            record["risk_score"] = float(raw_score) if raw_score is not None else None
        out.append(record)
    return out


def ensure_default_simulation_run(
    db: Session,
    simulation_id: str,
    simulation_name: str,
    as_of_date: date,
    thresholds: Sequence[dict[str, Any]],
    coverage_multiplier: float = 1.0,
) -> None:
    """Create the simulation_runs row if missing; reuse it if compatible.

    This helper only writes the minimum row necessary to satisfy the
    ``payout_results.simulation_id`` foreign key constraint. Richer
    scenario tracking is handled by ``src.insurance.simulation``.
    """
    threshold_config = {"tiers": [dict(t) for t in thresholds]}
    existing = db.execute(
        select(
            SimulationRun.simulation_id,
            SimulationRun.as_of_date,
            SimulationRun.threshold_config,
            SimulationRun.coverage_multiplier,
        ).where(SimulationRun.simulation_id == simulation_id)
    ).first()
    if existing is None:
        db.add(
            SimulationRun(
                simulation_id=simulation_id,
                simulation_name=simulation_name,
                as_of_date=as_of_date,
                threshold_config=threshold_config,
                coverage_multiplier=coverage_multiplier,
            )
        )
        db.flush()
        return

    _id, existing_date, existing_config, existing_multiplier = existing
    if existing_date != as_of_date:
        raise ValueError(
            f"simulation_runs[{simulation_id}] exists with as_of_date "
            f"{existing_date} (incoming {as_of_date}); use a fresh simulation_id."
        )
    if existing_config != threshold_config:
        raise ValueError(
            f"simulation_runs[{simulation_id}] exists with a different "
            f"threshold_config; use a fresh simulation_id."
        )
    if float(existing_multiplier) != float(coverage_multiplier):
        raise ValueError(
            f"simulation_runs[{simulation_id}] exists with coverage_multiplier "
            f"{existing_multiplier} (incoming {coverage_multiplier})."
        )


def generate_payout_records(
    db: Session,
    asset_ids: Sequence[str] | None = None,
    as_of_date: date | None = None,
    simulation_id: str | None = None,
    thresholds: Sequence[dict[str, Any]] | None = None,
    coverage_multiplier: float = 1.0,
    include_risk_band: bool = True,
) -> list[dict[str, Any]]:
    """Generate one payout record per asset with rainfall features."""
    sim_id = simulation_id or DEFAULT_PAYOUT_SIMULATION_ID
    rows = fetch_payout_inputs(db, asset_ids, as_of_date, include_risk_band)
    out: list[dict[str, Any]] = []
    for r in rows:
        record = calculate_asset_payout_record(
            asset_record={
                "asset_id": r["asset_id"],
                "coverage_limit": r["coverage_limit"],
            },
            rainfall_feature_record={
                "as_of_date": r["as_of_date"],
                "rainfall_3d_mm": r["rainfall_3d_mm"],
            },
            risk_score_record=(
                {"risk_band": r.get("risk_band")} if include_risk_band else None
            ),
            simulation_id=sim_id,
            thresholds=thresholds,
            coverage_multiplier=coverage_multiplier,
        )
        out.append(record)
    return out


def validate_payout_records(
    records: Iterable[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Validate every record + uniqueness on ``(simulation_id, asset_id)``."""
    seen: set[tuple[str, str]] = set()
    out: list[dict[str, Any]] = []
    for record in records:
        validated = PayoutResultRecord.model_validate(record)
        key = (validated.simulation_id, validated.asset_id)
        if key in seen:
            raise ValueError(
                f"Duplicate (simulation_id, asset_id) in payout batch: {key}"
            )
        seen.add(key)
        out.append(validated.model_dump())
    return out


def persist_payout_results(
    records: Sequence[dict[str, Any]],
    db: Session,
    replace_existing: bool = True,
) -> int:
    """Insert payout rows; replace or skip duplicates by `(simulation_id, asset_id)`."""
    if not records:
        return 0

    validated = validate_payout_records(records)
    pairs = [(r["simulation_id"], r["asset_id"]) for r in validated]

    try:
        if replace_existing:
            db.execute(
                delete(PayoutResult).where(
                    tuple_(
                        PayoutResult.simulation_id,
                        PayoutResult.asset_id,
                    ).in_(pairs)
                )
            )
            to_insert = validated
        else:
            existing_rows = db.execute(
                select(
                    PayoutResult.simulation_id,
                    PayoutResult.asset_id,
                ).where(
                    tuple_(
                        PayoutResult.simulation_id,
                        PayoutResult.asset_id,
                    ).in_(pairs)
                )
            ).all()
            existing_keys = {(row[0], row[1]) for row in existing_rows}
            if existing_keys:
                logger.warning(
                    "Skipping %d existing payout_results rows", len(existing_keys)
                )
            to_insert = [
                r
                for r in validated
                if (r["simulation_id"], r["asset_id"]) not in existing_keys
            ]

        orm_rows = [
            PayoutResult(
                simulation_id=r["simulation_id"],
                asset_id=r["asset_id"],
                rainfall_3d_mm=r["rainfall_3d_mm"],
                trigger_status=r["trigger_status"],
                payout_rate=r["payout_rate"],
                coverage_limit=r["coverage_limit"],
                estimated_payout=r["estimated_payout"],
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


def run_payout_simulation(
    db: Session,
    asset_ids: Sequence[str] | None = None,
    as_of_date: date | None = None,
    simulation_id: str | None = None,
    simulation_name: str | None = None,
    thresholds: Sequence[dict[str, Any]] | None = None,
    coverage_multiplier: float = DEFAULT_PAYOUT_COVERAGE_MULTIPLIER,
    replace_existing: bool = True,
    include_risk_band: bool = True,
) -> dict[str, Any]:
    """Run the parametric payout pipeline and return a structured summary."""
    effective_as_of = as_of_date or DEFAULT_AS_OF_DATE
    sim_id = simulation_id or DEFAULT_PAYOUT_SIMULATION_ID
    sim_name = simulation_name or DEFAULT_PAYOUT_SIMULATION_NAME
    if coverage_multiplier <= 0:
        raise ValueError(
            f"coverage_multiplier must be positive (got {coverage_multiplier})"
        )

    threshold_table = (
        validate_payout_thresholds(thresholds)
        if thresholds is not None
        else get_default_payout_thresholds()
    )

    n_assets = db.execute(select(func.count()).select_from(Asset)).scalar() or 0
    n_features = (
        db.execute(
            select(func.count())
            .select_from(RainfallFeature)
            .where(RainfallFeature.as_of_date == effective_as_of)
        ).scalar()
        or 0
    )

    if n_assets == 0:
        raise ValueError("No assets in database; cannot run payout simulation")
    if n_features == 0:
        raise ValueError(
            f"No rainfall_features for as_of_date={effective_as_of}; "
            f"run feature generation first"
        )

    ensure_default_simulation_run(
        db,
        simulation_id=sim_id,
        simulation_name=sim_name,
        as_of_date=effective_as_of,
        thresholds=threshold_table,
        coverage_multiplier=coverage_multiplier,
    )

    considered = len(asset_ids) if asset_ids is not None else int(n_assets)
    records = generate_payout_records(
        db,
        asset_ids=asset_ids,
        as_of_date=effective_as_of,
        simulation_id=sim_id,
        thresholds=threshold_table,
        coverage_multiplier=coverage_multiplier,
        include_risk_band=include_risk_band,
    )
    inserted = persist_payout_results(records, db, replace_existing)

    triggered = sum(1 for r in records if r["trigger_status"] == "triggered")
    not_triggered = sum(1 for r in records if r["trigger_status"] == "not_triggered")
    total_coverage = sum(r["coverage_limit"] for r in records)
    total_payout = sum(r["estimated_payout"] for r in records)
    avg_rate = (
        round(sum(r["payout_rate"] for r in records) / len(records), 4)
        if records
        else None
    )

    summary = {
        "simulation_id": sim_id,
        "simulation_name": sim_name,
        "as_of_date": effective_as_of,
        "coverage_multiplier": float(coverage_multiplier),
        "assets_considered": considered,
        "feature_records_available": int(n_features),
        "payout_records_generated": len(records),
        "payout_records_inserted": inserted,
        "triggered_assets": triggered,
        "not_triggered_assets": not_triggered,
        "total_coverage_limit": round(total_coverage, 2),
        "total_estimated_payout": round(total_payout, 2),
        "average_payout_rate": avg_rate,
        "replace_existing": replace_existing,
    }
    PayoutSimulationRunSummary.model_validate(summary)
    return summary


__all__ = [
    "DEFAULT_AS_OF_DATE",
    "build_payout_input_query",
    "calculate_asset_payout_record",
    "calculate_estimated_payout",
    "calculate_payout_rate",
    "calculate_trigger_status",
    "ensure_default_simulation_run",
    "fetch_payout_inputs",
    "generate_payout_records",
    "get_default_payout_thresholds",
    "persist_payout_results",
    "run_payout_simulation",
    "validate_payout_records",
    "validate_payout_thresholds",
]
