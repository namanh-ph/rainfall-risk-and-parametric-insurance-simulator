"""Tests confirming simulation orchestration reuses payout plumbing"""

from __future__ import annotations

import inspect
import json
from datetime import date

from src.insurance import payout as payout_module
from src.insurance import simulation as simulation_module
from src.insurance.simulation import (
    build_threshold_config,
    get_default_coverage_multiplier_scenarios,
    get_default_threshold_scenarios,
)


def test_simulation_module_imports_payout_helpers() -> None:
    """The simulation module must reuse payout helpers, not duplicate them"""
    source = inspect.getsource(simulation_module)
    assert "from src.insurance.payout import" in source
    for name in (
        "generate_payout_records",
        "persist_payout_results",
        "validate_payout_thresholds",
    ):
        assert name in source, f"simulation module must reuse {name}"


def test_simulation_module_does_not_redefine_payout_helpers() -> None:
    """Simulation must not redefine the payout functions"""
    sim_names = {name for name in dir(simulation_module) if not name.startswith("_")}
    redefined = {
        "calculate_payout_rate",
        "calculate_trigger_status",
        "calculate_estimated_payout",
        "build_payout_input_query",
        "fetch_payout_inputs",
    } & sim_names
    assert not redefined, f"simulation must not redefine payout helpers: {redefined}"


def test_simulation_module_does_not_reference_forbidden_tables() -> None:
    """Sensitivity orchestration must not touch ML or asset-generation tables"""
    source = inspect.getsource(simulation_module)
    for forbidden in (
        "model_training_data",
        "model_predictions",
        "generate_synthetic_assets",
        "load_static_assets_to_db",
    ):
        assert forbidden not in source, f"forbidden reference {forbidden!r} in simulation module"


def test_scenario_payout_records_use_scenario_simulation_id() -> None:
    """Every payout record returned by generate_payout_records must carry the scenario id"""
    # Indirect check via the public stub helper used in tests: the
    # calculate_asset_payout_record helper applies simulation_id
    asset = {"asset_id": "VIC0001", "coverage_limit": 200_000.0}
    feature = {"as_of_date": date(2025, 12, 31), "rainfall_3d_mm": 50.0}
    rec = payout_module.calculate_asset_payout_record(
        asset, feature, simulation_id="SWEEP_2025_T040"
    )
    assert rec["simulation_id"] == "SWEEP_2025_T040"


def test_default_threshold_config_is_json_serialisable() -> None:
    table = build_threshold_config(60, 90, 120)
    payload = {"tiers": table}
    text = json.dumps(payload)
    parsed = json.loads(text)
    assert parsed["tiers"][3]["max_rainfall_3d_mm"] is None


def test_default_threshold_scenarios_threshold_config_is_serialisable() -> None:
    scenarios = get_default_threshold_scenarios()
    for sc in scenarios:
        text = json.dumps({"tiers": sc["threshold_config"]})
        assert "min_rainfall_3d_mm" in text


def test_coverage_multiplier_scenarios_have_positive_multipliers() -> None:
    for sc in get_default_coverage_multiplier_scenarios():
        assert sc["coverage_multiplier"] > 0
