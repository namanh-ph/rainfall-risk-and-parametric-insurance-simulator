"""Tests for simulation tracking primitives"""

from __future__ import annotations

from datetime import date
from typing import Any

import pytest
from pydantic import ValidationError

from src.insurance.simulation import (
    build_simulation_id,
    build_threshold_config,
    calculate_portfolio_payout_summary,
    ensure_simulation_run,
    validate_simulation_config,
)


class _FakeRow:
    def __init__(self, *values: Any) -> None:
        self._values = values

    def __iter__(self):
        return iter(self._values)


class _FakeResult:
    def __init__(self, row: _FakeRow | None = None) -> None:
        self._row = row

    def first(self) -> _FakeRow | None:
        return self._row


class FakeSession:
    """SQLAlchemy session double for simulation_runs tests"""

    def __init__(
        self, *, existing_run: _FakeRow | None = None
    ) -> None:
        self.added: list[Any] = []
        self.executes: list[Any] = []
        self.flushed = False
        self._existing_run = existing_run

    def execute(self, statement: Any, params: Any | None = None) -> _FakeResult:
        self.executes.append(statement)
        compiled = str(statement).lower()
        if compiled.startswith("select"):
            return _FakeResult(self._existing_run)
        return _FakeResult()

    def add(self, obj: Any) -> None:
        self.added.append(obj)

    def flush(self) -> None:
        self.flushed = True


def test_build_threshold_config_creates_sorted_half_open_tiers() -> None:
    table = build_threshold_config(60, 90, 120)
    assert len(table) == 4
    assert table[0]["min_rainfall_3d_mm"] == 0.0
    assert table[0]["max_rainfall_3d_mm"] == 60.0
    assert table[0]["payout_rate"] == 0.0
    assert table[1]["min_rainfall_3d_mm"] == 60.0
    assert table[1]["max_rainfall_3d_mm"] == 90.0
    assert table[1]["payout_rate"] == 0.2
    assert table[2]["payout_rate"] == 0.5
    assert table[3]["max_rainfall_3d_mm"] is None
    assert table[3]["payout_rate"] == 1.0


def test_build_threshold_config_rejects_invalid_ordering() -> None:
    with pytest.raises(ValueError):
        build_threshold_config(100, 100, 200)
    with pytest.raises(ValueError):
        build_threshold_config(200, 150, 100)
    with pytest.raises(ValueError):
        build_threshold_config(0, 100, 200)


def test_simulation_id_for_threshold_sweep() -> None:
    sid = build_simulation_id("SWEEP", date(2025, 12, 31), threshold_1_mm=60)
    assert sid == "SWEEP_2025_T060"


def test_simulation_id_for_coverage_multiplier() -> None:
    assert (
        build_simulation_id("MULT", date(2025, 12, 31), coverage_multiplier=1.25)
        == "MULT_2025_X125"
    )
    assert (
        build_simulation_id("MULT", date(2025, 12, 31), coverage_multiplier=0.75)
        == "MULT_2025_X075"
    )
    assert (
        build_simulation_id("MULT", date(2025, 12, 31), coverage_multiplier=1.5)
        == "MULT_2025_X150"
    )


def test_simulation_id_uppercases_prefix() -> None:
    sid = build_simulation_id("sweep", date(2025, 1, 1), threshold_1_mm=100)
    assert sid == "SWEEP_2025_T100"


def test_simulation_id_rejects_empty_prefix() -> None:
    with pytest.raises(ValueError):
        build_simulation_id("", date(2025, 12, 31))


def _valid_config(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "simulation_id": "SWEEP_2025_T060",
        "simulation_name": "2025 moderate threshold sensitivity simulation",
        "as_of_date": date(2025, 12, 31),
        "threshold_config": build_threshold_config(60, 90, 120),
        "coverage_multiplier": 1.0,
    }
    base.update(overrides)
    return base


def test_validate_simulation_config_accepts_valid() -> None:
    out = validate_simulation_config(_valid_config())
    assert out["simulation_id"] == "SWEEP_2025_T060"
    assert out["coverage_multiplier"] == 1.0
    assert len(out["threshold_config"]) == 4


def test_validate_simulation_config_rejects_missing_simulation_id() -> None:
    bad = _valid_config()
    bad["simulation_id"] = ""
    with pytest.raises(ValidationError):
        validate_simulation_config(bad)


@pytest.mark.parametrize("multiplier", [0, -0.1, -1.0])
def test_validate_simulation_config_rejects_non_positive_multiplier(
    multiplier: float,
) -> None:
    with pytest.raises(ValidationError):
        validate_simulation_config(_valid_config(coverage_multiplier=multiplier))


def test_validate_simulation_config_rejects_invalid_thresholds() -> None:
    bad = _valid_config()
    bad["threshold_config"] = [
        {"min_rainfall_3d_mm": 0.0, "max_rainfall_3d_mm": 100.0, "payout_rate": 1.5},
    ]
    with pytest.raises(ValidationError):
        validate_simulation_config(bad)


def _record(
    payout_rate: float, estimated_payout: float, coverage_limit: float = 100_000.0
) -> dict[str, Any]:
    return {
        "simulation_id": "X",
        "asset_id": "A",
        "rainfall_3d_mm": 0.0,
        "trigger_status": "triggered" if payout_rate > 0 else "not_triggered",
        "payout_rate": payout_rate,
        "coverage_limit": coverage_limit,
        "estimated_payout": estimated_payout,
        "risk_band": None,
    }


def test_portfolio_summary_returns_correct_asset_count() -> None:
    records = [_record(0.0, 0.0), _record(0.2, 20_000), _record(0.5, 50_000), _record(1.0, 100_000)]
    summary = calculate_portfolio_payout_summary(records)
    assert summary["asset_count"] == 4


def test_portfolio_summary_triggered_and_not_triggered_counts() -> None:
    records = [
        _record(0.0, 0.0),
        _record(0.0, 0.0),
        _record(0.2, 20_000),
        _record(1.0, 100_000),
    ]
    summary = calculate_portfolio_payout_summary(records)
    assert summary["triggered_assets"] == 2
    assert summary["not_triggered_assets"] == 2


def test_portfolio_summary_total_estimated_payout() -> None:
    records = [_record(0.2, 20_000), _record(0.5, 50_000), _record(1.0, 100_000)]
    summary = calculate_portfolio_payout_summary(records)
    assert summary["total_estimated_payout"] == 170_000.0


def test_portfolio_summary_distribution_sums_to_asset_count() -> None:
    records = [
        _record(0.0, 0.0),
        _record(0.0, 0.0),
        _record(0.0, 0.0),
        _record(0.2, 20_000),
        _record(0.5, 50_000),
        _record(1.0, 100_000),
    ]
    summary = calculate_portfolio_payout_summary(records)
    assert sum(summary["payout_rate_distribution"].values()) == summary["asset_count"]
    assert summary["payout_rate_distribution"]["0.0"] == 3


def test_portfolio_summary_empty_records_returns_zeros() -> None:
    summary = calculate_portfolio_payout_summary([])
    assert summary["asset_count"] == 0
    assert summary["triggered_assets"] == 0
    assert summary["total_estimated_payout"] == 0
    assert summary["payout_rate_distribution"] == {}


def test_ensure_simulation_run_inserts_when_missing() -> None:
    session = FakeSession(existing_run=None)
    ensure_simulation_run(session, _valid_config())
    assert len(session.added) == 1
    assert session.flushed is True


def test_ensure_simulation_run_reuses_matching_existing() -> None:
    config = _valid_config()
    threshold_blob = {"tiers": [dict(t) for t in config["threshold_config"]]}
    session = FakeSession(
        existing_run=_FakeRow(
            config["simulation_id"],
            config["simulation_name"],
            config["as_of_date"],
            threshold_blob,
            config["coverage_multiplier"],
        )
    )
    ensure_simulation_run(session, config)
    assert session.added == []


def test_ensure_simulation_run_rejects_conflict_without_replace() -> None:
    config = _valid_config()
    different = {"tiers": [{"min_rainfall_3d_mm": 0.0, "max_rainfall_3d_mm": None, "payout_rate": 0.0}]}
    session = FakeSession(
        existing_run=_FakeRow(
            config["simulation_id"],
            "different name",
            config["as_of_date"],
            different,
            config["coverage_multiplier"],
        )
    )
    with pytest.raises(ValueError, match="conflicting config"):
        ensure_simulation_run(session, config)


def test_ensure_simulation_run_updates_when_replace_existing_true() -> None:
    config = _valid_config()
    session = FakeSession(
        existing_run=_FakeRow(
            config["simulation_id"],
            "different name",
            config["as_of_date"],
            {"tiers": []},
            config["coverage_multiplier"],
        )
    )
    ensure_simulation_run(session, config, replace_existing=True)
    updates = [s for s in session.executes if str(s).lower().startswith("update")]
    assert len(updates) == 1
