"""Reusable simulation tracking and threshold-sensitivity orchestration.

This module composes on top of the payout engine in
``src.insurance.payout``. Each scenario is materialised as one
``simulation_runs`` row (scenario-specific ``simulation_id``) plus one
``payout_results`` row per asset for that scenario. Threshold sensitivity
sweeps and coverage-multiplier sweeps share the same plumbing.

Per the contract:

- ``rainfall_features.rainfall_3d_mm`` is the only payout trigger input.
; ``risk_score`` and ``risk_band`` never influence payout calculation.
; Scenario IDs are compact and deterministic; e.g. ``SWEEP_2025_T060``,
  ``MULT_2025_X125``
"""

from __future__ import annotations

import logging
from collections import Counter
from collections.abc import Iterable, Sequence
from datetime import date
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from src.db.models import SimulationRun
from src.domain.constants import (
    DEFAULT_PAYOUT_COVERAGE_MULTIPLIER,
    DEFAULT_PAYOUT_SIMULATION_ID,
    DEFAULT_PAYOUT_SIMULATION_NAME,
)
from src.insurance.payout import (
    DEFAULT_AS_OF_DATE,
    generate_payout_records,
    get_default_payout_thresholds,
    persist_payout_results,
    validate_payout_thresholds,
)
from src.schemas.simulation import (
    CombinedSensitivityRunSummary,
    CoverageMultiplierSensitivityRunSummary,
    PortfolioPayoutSummary,
    SimulationConfig,
    SimulationScenarioResult,
    ThresholdSensitivityRunSummary,
)

logger = logging.getLogger(__name__)


def build_threshold_config(
    trigger_1_mm: float,
    trigger_2_mm: float,
    trigger_3_mm: float,
    payout_rate_1: float = 0.2,
    payout_rate_2: float = 0.5,
    payout_rate_3: float = 1.0,
) -> list[dict[str, Any]]:
    """Build a 4-tier payout threshold table.

    Tiers (half-open):
      ``[0, t1)``  → 0.0
      ``[t1, t2)`` → ``payout_rate_1``
      ``[t2, t3)`` → ``payout_rate_2``
      ``[t3, ∞)``  → ``payout_rate_3``
    """
    if not (0 < trigger_1_mm < trigger_2_mm < trigger_3_mm):
        raise ValueError(
            "Triggers must satisfy 0 < trigger_1_mm < trigger_2_mm < trigger_3_mm; "
            f"got ({trigger_1_mm}, {trigger_2_mm}, {trigger_3_mm})"
        )
    table: list[dict[str, Any]] = [
        {"min_rainfall_3d_mm": 0.0, "max_rainfall_3d_mm": float(trigger_1_mm), "payout_rate": 0.0},
        {
            "min_rainfall_3d_mm": float(trigger_1_mm),
            "max_rainfall_3d_mm": float(trigger_2_mm),
            "payout_rate": float(payout_rate_1),
        },
        {
            "min_rainfall_3d_mm": float(trigger_2_mm),
            "max_rainfall_3d_mm": float(trigger_3_mm),
            "payout_rate": float(payout_rate_2),
        },
        {
            "min_rainfall_3d_mm": float(trigger_3_mm),
            "max_rainfall_3d_mm": None,
            "payout_rate": float(payout_rate_3),
        },
    ]
    return validate_payout_thresholds(table)


def build_simulation_id(
    prefix: str,
    as_of_date: date,
    threshold_1_mm: float | None = None,
    coverage_multiplier: float | None = None,
) -> str:
    """Compose a compact deterministic simulation ID.

    Examples::

        build_simulation_id("SWEEP", date(2025,12,31), threshold_1_mm=60)
            → "SWEEP_2025_T060"
        build_simulation_id("MULT",  date(2025,12,31), coverage_multiplier=1.25)
            → "MULT_2025_X125"
    """
    if not prefix:
        raise ValueError("prefix must be non-empty")
    parts: list[str] = [prefix.upper(), str(as_of_date.year)]
    if threshold_1_mm is not None:
        parts.append(f"T{round(threshold_1_mm):03d}")
    if coverage_multiplier is not None:
        parts.append(f"X{round(coverage_multiplier * 100):03d}")
    return "_".join(parts)


_DEFAULT_THRESHOLD_SUITE = (
    # (key, trigger_1, trigger_2, trigger_3, name_template)
    ("baseline", 100.0, 150.0, 200.0, None),  # uses DEFAULT_PAYOUT_SIMULATION_NAME
    ("moderate", 60.0, 90.0, 120.0, "{year} moderate threshold sensitivity simulation"),
    ("sensitive", 40.0, 60.0, 80.0, "{year} sensitive threshold sensitivity simulation"),
    (
        "very_sensitive",
        20.0,
        35.0,
        50.0,
        "{year} very-sensitive threshold sensitivity simulation",
    ),
)


def get_default_threshold_scenarios(
    as_of_date: date | None = None,
) -> list[dict[str, Any]]:
    """Return the 4-scenario threshold-sensitivity suite"""
    d = as_of_date or DEFAULT_AS_OF_DATE
    scenarios: list[dict[str, Any]] = []
    for key, t1, t2, t3, name_template in _DEFAULT_THRESHOLD_SUITE:
        if key == "baseline":
            simulation_id = DEFAULT_PAYOUT_SIMULATION_ID
            simulation_name = DEFAULT_PAYOUT_SIMULATION_NAME
        else:
            simulation_id = build_simulation_id("SWEEP", d, threshold_1_mm=t1)
            simulation_name = name_template.format(year=d.year)  # type: ignore[union-attr]
        scenarios.append(
            {
                "simulation_id": simulation_id,
                "simulation_name": simulation_name,
                "as_of_date": d,
                "threshold_config": build_threshold_config(t1, t2, t3),
                "coverage_multiplier": DEFAULT_PAYOUT_COVERAGE_MULTIPLIER,
            }
        )
    return scenarios


_DEFAULT_COVERAGE_MULTIPLIERS = (0.75, 1.00, 1.25, 1.50)


def get_default_coverage_multiplier_scenarios(
    as_of_date: date | None = None,
) -> list[dict[str, Any]]:
    """Return the 4-scenario coverage-multiplier suite"""
    d = as_of_date or DEFAULT_AS_OF_DATE
    scenarios: list[dict[str, Any]] = []
    for multiplier in _DEFAULT_COVERAGE_MULTIPLIERS:
        scenarios.append(
            {
                "simulation_id": build_simulation_id(
                    "MULT", d, coverage_multiplier=multiplier
                ),
                "simulation_name": (
                    f"{d.year} coverage multiplier {multiplier:.2f} scenario"
                ),
                "as_of_date": d,
                "threshold_config": get_default_payout_thresholds(),
                "coverage_multiplier": float(multiplier),
            }
        )
    return scenarios


def validate_simulation_config(config: dict[str, Any]) -> dict[str, Any]:
    """Validate a scenario config + its threshold table. Returns a normalised dict"""
    parsed = SimulationConfig.model_validate(config)
    thresholds = validate_payout_thresholds(parsed.threshold_config)
    return {
        "simulation_id": parsed.simulation_id,
        "simulation_name": parsed.simulation_name,
        "as_of_date": parsed.as_of_date,
        "threshold_config": thresholds,
        "coverage_multiplier": float(parsed.coverage_multiplier),
    }


def _threshold_blob(thresholds: Iterable[dict[str, Any]]) -> dict[str, Any]:
    return {"tiers": [dict(t) for t in thresholds]}


def ensure_simulation_run(
    db: Session,
    config: dict[str, Any],
    replace_existing: bool = False,
) -> None:
    """Create / reuse / replace a ``simulation_runs`` row for ``config``.

    Behaviour:
     - row missing → INSERT
     - row exists and config matches → no-op
     - row exists, config differs, ``replace_existing=True`` → UPDATE
     - row exists, config differs, ``replace_existing=False`` → ``ValueError``
    """
    validated = validate_simulation_config(config)
    sim_id = validated["simulation_id"]
    threshold_blob = _threshold_blob(validated["threshold_config"])

    existing = db.execute(
        select(
            SimulationRun.simulation_id,
            SimulationRun.simulation_name,
            SimulationRun.as_of_date,
            SimulationRun.threshold_config,
            SimulationRun.coverage_multiplier,
        ).where(SimulationRun.simulation_id == sim_id)
    ).first()
    if existing is None:
        db.add(
            SimulationRun(
                simulation_id=sim_id,
                simulation_name=validated["simulation_name"],
                as_of_date=validated["as_of_date"],
                threshold_config=threshold_blob,
                coverage_multiplier=validated["coverage_multiplier"],
            )
        )
        db.flush()
        return

    _id, ex_name, ex_date, ex_config, ex_mult = existing
    matches = (
        ex_date == validated["as_of_date"]
        and ex_config == threshold_blob
        and float(ex_mult) == float(validated["coverage_multiplier"])
        and ex_name == validated["simulation_name"]
    )
    if matches:
        return

    if not replace_existing:
        raise ValueError(
            f"simulation_runs[{sim_id}] exists with conflicting config; "
            f"use replace_existing=True or a fresh simulation_id"
        )

    db.execute(
        update(SimulationRun)
        .where(SimulationRun.simulation_id == sim_id)
        .values(
            simulation_name=validated["simulation_name"],
            as_of_date=validated["as_of_date"],
            threshold_config=threshold_blob,
            coverage_multiplier=validated["coverage_multiplier"],
        )
    )
    db.flush()


def calculate_portfolio_payout_summary(
    records: Sequence[dict[str, Any]],
) -> dict[str, Any]:
    """Aggregate per-asset payout records into a portfolio-level summary"""
    asset_count = len(records)
    if asset_count == 0:
        summary = {
            "asset_count": 0,
            "triggered_assets": 0,
            "not_triggered_assets": 0,
            "trigger_rate": 0.0,
            "total_coverage_limit": 0.0,
            "total_estimated_payout": 0.0,
            "average_payout_rate": 0.0,
            "average_estimated_payout": 0.0,
            "max_estimated_payout": 0.0,
            "payout_rate_distribution": {},
        }
        PortfolioPayoutSummary.model_validate(summary)
        return summary

    triggered = sum(1 for r in records if r["trigger_status"] == "triggered")
    not_triggered = asset_count - triggered
    total_coverage = sum(float(r["coverage_limit"]) for r in records)
    total_payout = sum(float(r["estimated_payout"]) for r in records)
    avg_rate = sum(float(r["payout_rate"]) for r in records) / asset_count
    avg_payout = total_payout / asset_count
    max_payout = max(float(r["estimated_payout"]) for r in records)
    dist = Counter(f"{round(float(r['payout_rate']), 4)}" for r in records)
    summary = {
        "asset_count": asset_count,
        "triggered_assets": triggered,
        "not_triggered_assets": not_triggered,
        "trigger_rate": round(triggered / asset_count, 6),
        "total_coverage_limit": round(total_coverage, 2),
        "total_estimated_payout": round(total_payout, 2),
        "average_payout_rate": round(avg_rate, 6),
        "average_estimated_payout": round(avg_payout, 4),
        "max_estimated_payout": round(max_payout, 2),
        "payout_rate_distribution": dict(dist),
    }
    PortfolioPayoutSummary.model_validate(summary)
    return summary


def run_single_simulation(
    db: Session,
    config: dict[str, Any],
    asset_ids: Sequence[str] | None = None,
    replace_existing: bool = True,
    include_risk_band: bool = True,
) -> dict[str, Any]:
    """Run one scenario end-to-end and return a ``SimulationScenarioResult``-shaped dict"""
    validated = validate_simulation_config(config)
    ensure_simulation_run(db, validated, replace_existing=replace_existing)

    records = generate_payout_records(
        db,
        asset_ids=asset_ids,
        as_of_date=validated["as_of_date"],
        simulation_id=validated["simulation_id"],
        thresholds=validated["threshold_config"],
        coverage_multiplier=validated["coverage_multiplier"],
        include_risk_band=include_risk_band,
    )
    inserted = persist_payout_results(records, db, replace_existing=replace_existing)
    summary = calculate_portfolio_payout_summary(records)

    scenario_result = {
        "simulation_id": validated["simulation_id"],
        "simulation_name": validated["simulation_name"],
        "threshold_config": validated["threshold_config"],
        "coverage_multiplier": validated["coverage_multiplier"],
        "payout_records_generated": len(records),
        "payout_records_inserted": inserted,
        "summary": summary,
    }
    SimulationScenarioResult.model_validate(scenario_result)
    return scenario_result


def _run_scenarios(
    db: Session,
    scenarios: Sequence[dict[str, Any]],
    asset_ids: Sequence[str] | None,
    replace_existing: bool,
    include_risk_band: bool,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for scenario in scenarios:
        result = run_single_simulation(
            db,
            scenario,
            asset_ids=asset_ids,
            replace_existing=replace_existing,
            include_risk_band=include_risk_band,
        )
        out.append(result)
    return out


def run_threshold_sensitivity(
    db: Session,
    scenarios: Sequence[dict[str, Any]] | None = None,
    asset_ids: Sequence[str] | None = None,
    as_of_date: date | None = None,
    replace_existing: bool = True,
    include_risk_band: bool = True,
) -> dict[str, Any]:
    """Run the threshold-sensitivity suite and return a structured summary"""
    effective_as_of = as_of_date or DEFAULT_AS_OF_DATE
    scenario_list = (
        list(scenarios)
        if scenarios is not None
        else get_default_threshold_scenarios(effective_as_of)
    )
    if not scenario_list:
        raise ValueError("Threshold sensitivity requires at least one scenario")

    results = _run_scenarios(
        db, scenario_list, asset_ids, replace_existing, include_risk_band
    )
    summary = {
        "as_of_date": effective_as_of,
        "scenario_count": len(results),
        "scenarios": results,
        "replace_existing": replace_existing,
    }
    ThresholdSensitivityRunSummary.model_validate(summary)
    return summary


def run_coverage_multiplier_sensitivity(
    db: Session,
    scenarios: Sequence[dict[str, Any]] | None = None,
    asset_ids: Sequence[str] | None = None,
    as_of_date: date | None = None,
    replace_existing: bool = True,
    include_risk_band: bool = True,
) -> dict[str, Any]:
    """Run the coverage-multiplier sensitivity suite and return a summary"""
    effective_as_of = as_of_date or DEFAULT_AS_OF_DATE
    scenario_list = (
        list(scenarios)
        if scenarios is not None
        else get_default_coverage_multiplier_scenarios(effective_as_of)
    )
    if not scenario_list:
        raise ValueError("Coverage-multiplier sensitivity requires at least one scenario")

    results = _run_scenarios(
        db, scenario_list, asset_ids, replace_existing, include_risk_band
    )
    summary = {
        "as_of_date": effective_as_of,
        "scenario_count": len(results),
        "scenarios": results,
        "replace_existing": replace_existing,
    }
    CoverageMultiplierSensitivityRunSummary.model_validate(summary)
    return summary


def run_combined_sensitivity(
    db: Session,
    threshold_scenarios: Sequence[dict[str, Any]] | None = None,
    coverage_multiplier_scenarios: Sequence[dict[str, Any]] | None = None,
    asset_ids: Sequence[str] | None = None,
    as_of_date: date | None = None,
    replace_existing: bool = True,
    include_risk_band: bool = True,
) -> dict[str, Any]:
    """Run both sensitivity suites and bundle the results"""
    effective_as_of = as_of_date or DEFAULT_AS_OF_DATE
    threshold = run_threshold_sensitivity(
        db,
        scenarios=threshold_scenarios,
        asset_ids=asset_ids,
        as_of_date=effective_as_of,
        replace_existing=replace_existing,
        include_risk_band=include_risk_band,
    )
    multiplier = run_coverage_multiplier_sensitivity(
        db,
        scenarios=coverage_multiplier_scenarios,
        asset_ids=asset_ids,
        as_of_date=effective_as_of,
        replace_existing=replace_existing,
        include_risk_band=include_risk_band,
    )
    summary = {
        "as_of_date": effective_as_of,
        "threshold_sensitivity": threshold,
        "coverage_multiplier_sensitivity": multiplier,
        "replace_existing": replace_existing,
    }
    CombinedSensitivityRunSummary.model_validate(summary)
    return summary


__all__ = [
    "build_simulation_id",
    "build_threshold_config",
    "calculate_portfolio_payout_summary",
    "ensure_simulation_run",
    "get_default_coverage_multiplier_scenarios",
    "get_default_threshold_scenarios",
    "run_combined_sensitivity",
    "run_coverage_multiplier_sensitivity",
    "run_single_simulation",
    "run_threshold_sensitivity",
    "validate_simulation_config",
]
