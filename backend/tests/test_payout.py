"""Tests for the parametric payout engine"""

from __future__ import annotations

from datetime import date
from typing import Any

import pytest
from pydantic import ValidationError

from src.db.models import PayoutResult
from src.insurance.payout import (
    calculate_asset_payout_record,
    calculate_estimated_payout,
    calculate_payout_rate,
    calculate_trigger_status,
    get_default_payout_thresholds,
    persist_payout_results,
    validate_payout_records,
    validate_payout_thresholds,
)
from src.schemas.payout import PayoutResultRecord


class _FakeResult:
    def __init__(self, rows: list[Any] | None = None) -> None:
        self._rows = rows or []

    def all(self) -> list[Any]:
        return self._rows


class FakeSession:
    def __init__(
        self, *, existing_pairs: set[tuple[str, str]] | None = None
    ) -> None:
        self.executes: list[Any] = []
        self.added: list[Any] = []
        self.committed = False
        self.rolled_back = False
        self._existing_pairs = set(existing_pairs or ())

    def execute(self, statement: Any, params: Any | None = None) -> _FakeResult:
        self.executes.append(statement)
        compiled = str(statement).lower()
        if compiled.startswith("delete"):
            return _FakeResult()
        if compiled.startswith("select") and "payout_results" in compiled:
            return _FakeResult(rows=list(self._existing_pairs))
        return _FakeResult()

    def add_all(self, objs: list[Any]) -> None:
        self.added.extend(objs)

    def commit(self) -> None:
        self.committed = True

    def rollback(self) -> None:
        self.rolled_back = True

    def close(self) -> None:  # pragma: no cover
        pass


def test_default_thresholds_are_canonical() -> None:
    table = get_default_payout_thresholds()
    assert len(table) == 4
    rates = [t["payout_rate"] for t in table]
    assert rates == [0.0, 0.2, 0.5, 1.0]
    assert table[-1]["max_rainfall_3d_mm"] is None


def test_validate_payout_thresholds_accepts_canonical() -> None:
    table = validate_payout_thresholds(get_default_payout_thresholds())
    assert [t["payout_rate"] for t in table] == [0.0, 0.2, 0.5, 1.0]


def test_validate_payout_thresholds_rejects_overlap() -> None:
    bad = [
        {"min_rainfall_3d_mm": 0.0, "max_rainfall_3d_mm": 100.0, "payout_rate": 0.0},
        {"min_rainfall_3d_mm": 80.0, "max_rainfall_3d_mm": 150.0, "payout_rate": 0.2},
    ]
    with pytest.raises(ValueError, match="overlap"):
        validate_payout_thresholds(bad)


def test_validate_payout_thresholds_rejects_invalid_rate() -> None:
    bad = [
        {"min_rainfall_3d_mm": 0.0, "max_rainfall_3d_mm": 100.0, "payout_rate": 1.5},
    ]
    with pytest.raises(ValidationError):
        validate_payout_thresholds(bad)


def test_validate_payout_thresholds_rejects_max_le_min() -> None:
    bad = [
        {"min_rainfall_3d_mm": 100.0, "max_rainfall_3d_mm": 100.0, "payout_rate": 0.5},
    ]
    with pytest.raises(ValidationError):
        validate_payout_thresholds(bad)


def test_validate_payout_thresholds_rejects_open_ended_in_middle() -> None:
    bad = [
        {"min_rainfall_3d_mm": 0.0, "max_rainfall_3d_mm": None, "payout_rate": 0.0},
        {"min_rainfall_3d_mm": 100.0, "max_rainfall_3d_mm": 150.0, "payout_rate": 0.2},
    ]
    with pytest.raises(ValueError, match="open-ended"):
        validate_payout_thresholds(bad)


@pytest.mark.parametrize(
    ("rainfall", "expected"),
    [
        (0.0, 0.0),
        (99.999, 0.0),
        (100.0, 0.2),
        (149.999, 0.2),
        (150.0, 0.5),
        (199.999, 0.5),
        (200.0, 1.0),
        (1000.0, 1.0),
    ],
)
def test_payout_rate_at_canonical_thresholds(rainfall: float, expected: float) -> None:
    assert calculate_payout_rate(rainfall) == expected


def test_payout_rate_rejects_negative_rainfall() -> None:
    with pytest.raises(ValueError):
        calculate_payout_rate(-1.0)


def test_trigger_status_zero_is_not_triggered() -> None:
    assert calculate_trigger_status(0.0) == "not_triggered"


@pytest.mark.parametrize("rate", [0.2, 0.5, 1.0])
def test_trigger_status_positive_is_triggered(rate: float) -> None:
    assert calculate_trigger_status(rate) == "triggered"


def test_trigger_status_rejects_out_of_range() -> None:
    with pytest.raises(ValueError):
        calculate_trigger_status(1.5)
    with pytest.raises(ValueError):
        calculate_trigger_status(-0.01)


def test_estimated_payout_uses_canonical_formula() -> None:
    assert calculate_estimated_payout(200_000, 0.5, coverage_multiplier=1.0) == 100_000
    assert calculate_estimated_payout(200_000, 1.0, coverage_multiplier=1.5) == 300_000


def test_estimated_payout_rejects_negative_coverage_limit() -> None:
    with pytest.raises(ValueError):
        calculate_estimated_payout(-1, 0.5)


def test_estimated_payout_rejects_invalid_payout_rate() -> None:
    with pytest.raises(ValueError):
        calculate_estimated_payout(100_000, 1.5)
    with pytest.raises(ValueError):
        calculate_estimated_payout(100_000, -0.1)


def test_estimated_payout_rejects_non_positive_multiplier() -> None:
    with pytest.raises(ValueError):
        calculate_estimated_payout(100_000, 0.5, coverage_multiplier=0.0)


def _asset() -> dict[str, Any]:
    return {"asset_id": "VIC0001", "coverage_limit": 200_000.0}


def _feature(rainfall_3d_mm: float) -> dict[str, Any]:
    return {"as_of_date": date(2025, 12, 31), "rainfall_3d_mm": rainfall_3d_mm}


def test_record_contains_all_canonical_fields() -> None:
    rec = calculate_asset_payout_record(_asset(), _feature(160.0))
    expected = {
        "simulation_id",
        "asset_id",
        "rainfall_3d_mm",
        "trigger_status",
        "payout_rate",
        "coverage_limit",
        "estimated_payout",
        "risk_band",
    }
    assert set(rec.keys()) == expected


def test_record_estimated_payout_matches_formula() -> None:
    rec = calculate_asset_payout_record(_asset(), _feature(160.0))
    assert rec["payout_rate"] == 0.5
    assert rec["estimated_payout"] == 100_000.0
    assert rec["trigger_status"] == "triggered"


def test_record_below_threshold_yields_zero_payout() -> None:
    rec = calculate_asset_payout_record(_asset(), _feature(50.0))
    assert rec["payout_rate"] == 0.0
    assert rec["estimated_payout"] == 0.0
    assert rec["trigger_status"] == "not_triggered"


def test_record_picks_up_optional_risk_band() -> None:
    rec = calculate_asset_payout_record(
        _asset(),
        _feature(160.0),
        risk_score_record={"risk_band": "High"},
    )
    assert rec["risk_band"] == "High"


def test_record_risk_band_does_not_affect_payout_rate() -> None:
    for band in ("Low", "Medium", "High", "Severe", None):
        rec = calculate_asset_payout_record(
            _asset(),
            _feature(160.0),
            risk_score_record=({"risk_band": band} if band is not None else None),
        )
        assert rec["payout_rate"] == 0.5
        assert rec["estimated_payout"] == 100_000.0


def test_record_uses_coverage_multiplier() -> None:
    rec = calculate_asset_payout_record(
        _asset(), _feature(200.0), coverage_multiplier=1.5
    )
    assert rec["estimated_payout"] == 300_000.0


def _good_record(asset_id: str = "VIC0001") -> dict[str, Any]:
    return {
        "simulation_id": "DEFAULT_2025_BASELINE",
        "asset_id": asset_id,
        "rainfall_3d_mm": 160.0,
        "trigger_status": "triggered",
        "payout_rate": 0.5,
        "coverage_limit": 200_000.0,
        "estimated_payout": 100_000.0,
        "risk_band": "High",
    }


def test_schema_validates_good_record() -> None:
    rec = PayoutResultRecord.model_validate(_good_record())
    assert rec.trigger_status == "triggered"


@pytest.mark.parametrize("status", ["fired", "yes", "n/a", ""])
def test_schema_rejects_invalid_trigger_status(status: str) -> None:
    bad = _good_record()
    bad["trigger_status"] = status
    with pytest.raises(ValidationError):
        PayoutResultRecord.model_validate(bad)


@pytest.mark.parametrize("rate", [-0.1, 1.1, 2.0])
def test_schema_rejects_invalid_payout_rate(rate: float) -> None:
    bad = _good_record()
    bad["payout_rate"] = rate
    bad["trigger_status"] = "triggered" if rate > 0 else "not_triggered"
    with pytest.raises(ValidationError):
        PayoutResultRecord.model_validate(bad)


def test_schema_rejects_inconsistent_trigger_status_zero_rate() -> None:
    bad = _good_record()
    bad["payout_rate"] = 0.0
    bad["estimated_payout"] = 0.0
    # trigger_status still 'triggered' → inconsistent
    with pytest.raises(ValidationError):
        PayoutResultRecord.model_validate(bad)


def test_schema_accepts_null_risk_band() -> None:
    rec = _good_record()
    rec["risk_band"] = None
    parsed = PayoutResultRecord.model_validate(rec)
    assert parsed.risk_band is None


def test_schema_rejects_invalid_risk_band() -> None:
    rec = _good_record()
    rec["risk_band"] = "Critical"
    with pytest.raises(ValidationError):
        PayoutResultRecord.model_validate(rec)


def test_validate_accepts_unique_records() -> None:
    out = validate_payout_records([_good_record("VIC0001"), _good_record("VIC0002")])
    assert len(out) == 2


def test_validate_rejects_duplicate_simulation_asset() -> None:
    with pytest.raises(ValueError, match="Duplicate"):
        validate_payout_records([_good_record("VIC0001"), _good_record("VIC0001")])


def test_persist_inserts_all_when_replace_existing_true() -> None:
    records = [_good_record("VIC0001"), _good_record("VIC0002")]
    session = FakeSession()
    n = persist_payout_results(records, session, replace_existing=True)
    assert n == 2
    assert all(isinstance(o, PayoutResult) for o in session.added)
    assert session.committed is True


def test_persist_replace_existing_issues_delete_first() -> None:
    records = [_good_record("VIC0001")]
    session = FakeSession()
    persist_payout_results(records, session, replace_existing=True)
    deletes = [s for s in session.executes if str(s).lower().startswith("delete")]
    assert len(deletes) == 1


def test_persist_skips_existing_when_replace_existing_false() -> None:
    records = [_good_record("VIC0001"), _good_record("VIC0002")]
    session = FakeSession(
        existing_pairs={("DEFAULT_2025_BASELINE", "VIC0001")}
    )
    n = persist_payout_results(records, session, replace_existing=False)
    assert n == 1
    assert {o.asset_id for o in session.added} == {"VIC0002"}


def test_persist_validates_before_insert() -> None:
    bad = _good_record()
    bad["payout_rate"] = 1.5
    session = FakeSession()
    with pytest.raises(ValidationError):
        persist_payout_results([bad], session)
    assert session.committed is False


def test_persist_rolls_back_on_failure() -> None:
    records = [_good_record("VIC0001")]

    class Boom(FakeSession):
        def add_all(self, objs: list[Any]) -> None:
            raise RuntimeError("boom")

    session = Boom()
    with pytest.raises(RuntimeError):
        persist_payout_results(records, session)
    assert session.rolled_back is True
    assert session.committed is False


def test_persist_returns_zero_for_empty_input() -> None:
    session = FakeSession()
    assert persist_payout_results([], session) == 0
    assert session.committed is False
