"""Simulation HTTP endpoints (POST).

Persists payout_results and simulation_runs.
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, status
from sqlalchemy.orm import Session

from src.api.deps import get_db
from src.insurance.payout import run_payout_simulation
from src.insurance.simulation import (
    run_combined_sensitivity,
    run_coverage_multiplier_sensitivity,
    run_threshold_sensitivity,
)
from src.schemas.api_simulation import (
    PayoutSimulationRequest,
    PayoutSimulationResponse,
    ThresholdSensitivityRequest,
    ThresholdSensitivityResponse,
    ThresholdSensitivityScenarioResponse,
)

logger = logging.getLogger(__name__)
router = APIRouter(tags=["simulation"])


@router.post("/simulate/payout", response_model=PayoutSimulationResponse)
def simulate_payout(
    body: PayoutSimulationRequest = Body(...),
    db: Session = Depends(get_db),
) -> PayoutSimulationResponse:
    try:
        summary = run_payout_simulation(
            db,
            asset_ids=body.asset_ids,
            as_of_date=body.as_of_date,
            simulation_id=body.simulation_id,
            simulation_name=body.simulation_name,
            coverage_multiplier=body.coverage_multiplier,
            replace_existing=body.replace_existing,
            include_risk_band=body.include_risk_band,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc

    return PayoutSimulationResponse.model_validate(summary)


def _scenario_to_response(scenario: dict[str, Any]) -> dict[str, Any]:
    """Flatten the service's scenario result into the API response shape."""
    summary = scenario.get("summary") or {}
    return {
        "simulation_id": scenario["simulation_id"],
        "simulation_name": scenario["simulation_name"],
        "coverage_multiplier": float(scenario["coverage_multiplier"]),
        "payout_records_generated": int(scenario["payout_records_generated"]),
        "payout_records_inserted": int(scenario["payout_records_inserted"]),
        "asset_count": int(summary.get("asset_count") or 0),
        "triggered_assets": int(summary.get("triggered_assets") or 0),
        "not_triggered_assets": int(summary.get("not_triggered_assets") or 0),
        "trigger_rate": float(summary.get("trigger_rate") or 0.0),
        "total_coverage_limit": float(summary.get("total_coverage_limit") or 0.0),
        "total_estimated_payout": float(summary.get("total_estimated_payout") or 0.0),
        "average_payout_rate": float(summary.get("average_payout_rate") or 0.0),
    }


@router.post(
    "/simulate/threshold-sensitivity",
    response_model=ThresholdSensitivityResponse,
)
def simulate_threshold_sensitivity(
    body: ThresholdSensitivityRequest = Body(...),
    db: Session = Depends(get_db),
) -> ThresholdSensitivityResponse:
    try:
        scenarios: list[dict[str, Any]] = []
        if body.mode == "thresholds":
            summary = run_threshold_sensitivity(
                db,
                asset_ids=body.asset_ids,
                as_of_date=body.as_of_date,
                replace_existing=body.replace_existing,
                include_risk_band=body.include_risk_band,
            )
            scenarios = summary["scenarios"]
        elif body.mode == "coverage_multipliers":
            summary = run_coverage_multiplier_sensitivity(
                db,
                asset_ids=body.asset_ids,
                as_of_date=body.as_of_date,
                replace_existing=body.replace_existing,
                include_risk_band=body.include_risk_band,
            )
            scenarios = summary["scenarios"]
        else:  # combined
            summary = run_combined_sensitivity(
                db,
                asset_ids=body.asset_ids,
                as_of_date=body.as_of_date,
                replace_existing=body.replace_existing,
                include_risk_band=body.include_risk_band,
            )
            scenarios = (
                summary["threshold_sensitivity"]["scenarios"]
                + summary["coverage_multiplier_sensitivity"]["scenarios"]
            )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc

    items = [
        ThresholdSensitivityScenarioResponse.model_validate(_scenario_to_response(s))
        for s in scenarios
    ]
    return ThresholdSensitivityResponse(
        as_of_date=_resolve_as_of_date(body.as_of_date),
        mode=body.mode,
        scenario_count=len(items),
        scenarios=items,
        replace_existing=body.replace_existing,
    )


def _resolve_as_of_date(value: date) -> date:
    return value


__all__ = ["router"]
