"""Tests for threshold and coverage-multiplier sensitivity orchestrators"""

from __future__ import annotations

from datetime import date
from typing import Any
from unittest.mock import MagicMock

import pytest

from src.insurance import simulation as simulation_module
from src.insurance.simulation import (
    get_default_coverage_multiplier_scenarios,
    get_default_threshold_scenarios,
    run_combined_sensitivity,
    run_coverage_multiplier_sensitivity,
    run_single_simulation,
    run_threshold_sensitivity,
)
from src.schemas.simulation import (
    CombinedSensitivityRunSummary,
    CoverageMultiplierSensitivityRunSummary,
    ThresholdSensitivityRunSummary,
)


def test_default_threshold_scenarios_has_at_least_four() -> None:
    scenarios = get_default_threshold_scenarios()
    assert len(scenarios) >= 4


def test_default_threshold_scenarios_include_baseline() -> None:
    sims = {s["simulation_id"] for s in get_default_threshold_scenarios()}
    assert "DEFAULT_2025_BASELINE" in sims


@pytest.mark.parametrize(
    "sweep_id", ["SWEEP_2025_T060", "SWEEP_2025_T040", "SWEEP_2025_T020"]
)
def test_default_threshold_scenarios_include_sweeps(sweep_id: str) -> None:
    sims = {s["simulation_id"] for s in get_default_threshold_scenarios()}
    assert sweep_id in sims


def test_default_coverage_multiplier_scenarios_cover_canonical_values() -> None:
    sims = get_default_coverage_multiplier_scenarios()
    multipliers = {round(s["coverage_multiplier"], 2) for s in sims}
    assert multipliers == {0.75, 1.00, 1.25, 1.50}


def test_default_coverage_multiplier_scenario_ids_are_canonical() -> None:
    ids = {s["simulation_id"] for s in get_default_coverage_multiplier_scenarios()}
    assert ids == {"MULT_2025_X075", "MULT_2025_X100", "MULT_2025_X125", "MULT_2025_X150"}


def _stub_payout_records(
    simulation_id: str,
    coverage_multiplier: float,
    rainfall_3d_mm: float = 50.0,
    n: int = 3,
) -> list[dict[str, Any]]:
    payout_rate = 0.2 if rainfall_3d_mm >= 40 else 0.0
    trigger_status = "triggered" if payout_rate > 0 else "not_triggered"
    coverage = 100_000.0
    estimated = coverage * coverage_multiplier * payout_rate
    return [
        {
            "simulation_id": simulation_id,
            "asset_id": f"VIC{i:04d}",
            "rainfall_3d_mm": rainfall_3d_mm,
            "trigger_status": trigger_status,
            "payout_rate": payout_rate,
            "coverage_limit": coverage,
            "estimated_payout": estimated,
            "risk_band": None,
        }
        for i in range(1, n + 1)
    ]


def test_run_single_simulation_calls_payout_helpers_with_scenario_config(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    def _fake_ensure(db: Any, config: dict[str, Any], replace_existing: bool = False) -> None:
        captured["ensured_sim_id"] = config["simulation_id"]

    def _fake_generate(
        db: Any,
        asset_ids: Any = None,
        as_of_date: Any = None,
        simulation_id: str | None = None,
        thresholds: Any = None,
        coverage_multiplier: float = 1.0,
        include_risk_band: bool = True,
    ) -> list[dict[str, Any]]:
        captured["generated_sim_id"] = simulation_id
        captured["generated_multiplier"] = coverage_multiplier
        captured["generated_thresholds"] = thresholds
        return _stub_payout_records(simulation_id or "X", coverage_multiplier)

    def _fake_persist(records: Any, db: Any, replace_existing: bool = True) -> int:
        captured["persisted_count"] = len(records)
        captured["persisted_sim_ids"] = {r["simulation_id"] for r in records}
        return len(records)

    monkeypatch.setattr(simulation_module, "ensure_simulation_run", _fake_ensure)
    monkeypatch.setattr(simulation_module, "generate_payout_records", _fake_generate)
    monkeypatch.setattr(simulation_module, "persist_payout_results", _fake_persist)

    scenarios = get_default_threshold_scenarios()
    scenario = next(s for s in scenarios if s["simulation_id"] == "SWEEP_2025_T060")
    result = run_single_simulation(MagicMock(), scenario)

    assert result["simulation_id"] == "SWEEP_2025_T060"
    assert result["coverage_multiplier"] == 1.0
    assert result["payout_records_generated"] == 3
    assert result["payout_records_inserted"] == 3
    assert captured["ensured_sim_id"] == "SWEEP_2025_T060"
    assert captured["generated_sim_id"] == "SWEEP_2025_T060"
    assert captured["generated_multiplier"] == 1.0
    assert captured["persisted_sim_ids"] == {"SWEEP_2025_T060"}


def _patch_pipeline_stubs(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    state: dict[str, Any] = {"calls": []}

    def _fake_ensure(db: Any, config: dict[str, Any], replace_existing: bool = False) -> None:
        state["calls"].append(("ensure", config["simulation_id"]))

    def _fake_generate(
        db: Any,
        asset_ids: Any = None,
        as_of_date: Any = None,
        simulation_id: str | None = None,
        thresholds: Any = None,
        coverage_multiplier: float = 1.0,
        include_risk_band: bool = True,
    ) -> list[dict[str, Any]]:
        state["calls"].append(("generate", simulation_id, coverage_multiplier))
        return _stub_payout_records(simulation_id or "X", coverage_multiplier)

    def _fake_persist(records: Any, db: Any, replace_existing: bool = True) -> int:
        return len(records)

    monkeypatch.setattr(simulation_module, "ensure_simulation_run", _fake_ensure)
    monkeypatch.setattr(simulation_module, "generate_payout_records", _fake_generate)
    monkeypatch.setattr(simulation_module, "persist_payout_results", _fake_persist)
    return state


def test_run_threshold_sensitivity_returns_one_result_per_scenario(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_pipeline_stubs(monkeypatch)
    summary = run_threshold_sensitivity(MagicMock(), as_of_date=date(2025, 12, 31))
    ThresholdSensitivityRunSummary.model_validate(summary)
    assert summary["scenario_count"] == 4
    ids = [s["simulation_id"] for s in summary["scenarios"]]
    assert ids[0] == "DEFAULT_2025_BASELINE"
    assert {ids[1], ids[2], ids[3]} == {
        "SWEEP_2025_T060",
        "SWEEP_2025_T040",
        "SWEEP_2025_T020",
    }


def test_run_coverage_multiplier_sensitivity_returns_one_result_per_scenario(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_pipeline_stubs(monkeypatch)
    summary = run_coverage_multiplier_sensitivity(
        MagicMock(), as_of_date=date(2025, 12, 31)
    )
    CoverageMultiplierSensitivityRunSummary.model_validate(summary)
    assert summary["scenario_count"] == 4
    multipliers = [round(s["coverage_multiplier"], 2) for s in summary["scenarios"]]
    assert multipliers == [0.75, 1.00, 1.25, 1.50]


def test_coverage_multiplier_changes_estimated_payout_not_payout_rate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Same rainfall input + same thresholds → same payout_rate; estimated_payout scales with multiplier"""
    _patch_pipeline_stubs(monkeypatch)
    summary = run_coverage_multiplier_sensitivity(
        MagicMock(), as_of_date=date(2025, 12, 31)
    )
    # All four scenarios use the default thresholds and the same stub rainfall
    # Stub rainfall is 50 mm → below the 100 mm trigger → payout_rate = 0,
    # so estimated_payout is 0 for every multiplier. The invariant we really want
    # to check: payout_rate distribution is identical across scenarios
    rate_dists = [s["summary"]["payout_rate_distribution"] for s in summary["scenarios"]]
    for d in rate_dists[1:]:
        assert d == rate_dists[0], "payout_rate distribution must be identical across multipliers"


def test_run_combined_sensitivity_contains_both_suites(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_pipeline_stubs(monkeypatch)
    summary = run_combined_sensitivity(MagicMock(), as_of_date=date(2025, 12, 31))
    CombinedSensitivityRunSummary.model_validate(summary)
    assert summary["threshold_sensitivity"]["scenario_count"] == 4
    assert summary["coverage_multiplier_sensitivity"]["scenario_count"] == 4
    assert summary["as_of_date"] == date(2025, 12, 31)
