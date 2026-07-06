"""Tests for asset-to-LGA spatial join validation and persistence"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from pydantic import ValidationError

from src.geospatial.lga_join import (
    fetch_asset_lga_assignments,
    persist_asset_lga_assignments,
    run_asset_lga_assignment,
    validate_lga_assignments,
)
from src.schemas.lga_join import (
    AssetLgaAssignmentRecord,
    AssetLgaAssignmentRunSummary,
)


class _FakeRow:
    def __init__(self, **kwargs: Any) -> None:
        self._data = kwargs

    @property
    def _mapping(self) -> dict[str, Any]:
        return self._data


class _FakeResult:
    def __init__(
        self, rows: list[Any] | None = None, scalar_value: Any = None
    ) -> None:
        self._rows = rows or []
        self._scalar = scalar_value

    def all(self) -> list[Any]:
        return self._rows

    def scalar(self) -> Any:
        return self._scalar

    def __iter__(self):
        return iter(self._rows)


class FakeSession:
    """SQLAlchemy session double for LGA-assignment tests"""

    def __init__(
        self,
        *,
        n_assets: int = 0,
        n_lgas: int = 0,
        join_rows: list[_FakeRow] | None = None,
        already_set_ids: set[str] | None = None,
    ) -> None:
        self.executes: list[Any] = []
        self.committed = False
        self.rolled_back = False
        self._n_assets = n_assets
        self._n_lgas = n_lgas
        self._join_rows = join_rows or []
        self._already_set = set(already_set_ids or ())

    def execute(self, statement: Any, params: Any | None = None) -> _FakeResult:
        self.executes.append(statement)
        compiled = str(statement).lower()
        if compiled.startswith("update"):
            return _FakeResult()
        # asset-LGA join CTE query
        if "polygon_candidates" in compiled and "ranked" in compiled:
            return _FakeResult(rows=self._join_rows)
        if "count(" in compiled and "from assets" in compiled:
            return _FakeResult(scalar_value=self._n_assets)
        if "count(" in compiled and "from lga_boundaries" in compiled:
            return _FakeResult(scalar_value=self._n_lgas)
        # existing-id select for replace_existing=False path
        if compiled.startswith("select") and "lga_code" in compiled:
            return _FakeResult(
                rows=[(aid, "LGA20660") for aid in self._already_set]
            )
        return _FakeResult()

    def commit(self) -> None:
        self.committed = True

    def rollback(self) -> None:
        self.rolled_back = True

    def close(self) -> None:  # pragma: no cover
        pass

    def update_count(self) -> int:
        """How many UPDATE statements were issued"""
        return sum(1 for s in self.executes if str(s).lower().startswith("update"))


def _now() -> datetime:
    return datetime.now(UTC)


def _covers_record(asset_id: str = "VIC0001") -> dict[str, Any]:
    return {
        "asset_id": asset_id,
        "lga_code": "LGA20660",
        "lga_name": "Melbourne",
        "assignment_method": "covers",
        "assignment_distance_km": 0.0,
        "assigned_at": _now(),
    }


def _intersects_record(asset_id: str = "VIC0001") -> dict[str, Any]:
    return {
        "asset_id": asset_id,
        "lga_code": "LGA20660",
        "lga_name": "Melbourne",
        "assignment_method": "intersects",
        "assignment_distance_km": 0.0,
        "assigned_at": _now(),
    }


def _fallback_record(asset_id: str = "VIC0002", distance: float = 4.5) -> dict[str, Any]:
    return {
        "asset_id": asset_id,
        "lga_code": "LGA22750",
        "lga_name": "Greater Geelong",
        "assignment_method": "nearest_fallback",
        "assignment_distance_km": distance,
        "assigned_at": _now(),
    }


def _unmatched_record(asset_id: str = "VIC0003") -> dict[str, Any]:
    return {
        "asset_id": asset_id,
        "lga_code": None,
        "lga_name": None,
        "assignment_method": "unmatched",
        "assignment_distance_km": None,
        "assigned_at": _now(),
    }


def test_record_validates_covers_assignment() -> None:
    rec = AssetLgaAssignmentRecord.model_validate(_covers_record())
    assert rec.assignment_method == "covers"


def test_record_validates_intersects_assignment() -> None:
    rec = AssetLgaAssignmentRecord.model_validate(_intersects_record())
    assert rec.assignment_method == "intersects"


def test_record_validates_nearest_fallback_assignment() -> None:
    rec = AssetLgaAssignmentRecord.model_validate(_fallback_record())
    assert rec.assignment_method == "nearest_fallback"
    assert rec.assignment_distance_km == 4.5


def test_record_validates_unmatched_assignment() -> None:
    rec = AssetLgaAssignmentRecord.model_validate(_unmatched_record())
    assert rec.assignment_method == "unmatched"
    assert rec.lga_code is None


@pytest.mark.parametrize("method", ["unknown", "exact", "outside", "fallback"])
def test_record_rejects_invalid_assignment_method(method: str) -> None:
    bad = _covers_record()
    bad["assignment_method"] = method
    with pytest.raises(ValidationError):
        AssetLgaAssignmentRecord.model_validate(bad)


def test_record_rejects_negative_nearest_fallback_distance() -> None:
    bad = _fallback_record()
    bad["assignment_distance_km"] = -1.0
    with pytest.raises(ValidationError):
        AssetLgaAssignmentRecord.model_validate(bad)


def test_record_rejects_non_zero_covers_distance() -> None:
    bad = _covers_record()
    bad["assignment_distance_km"] = 0.5
    with pytest.raises(ValidationError):
        AssetLgaAssignmentRecord.model_validate(bad)


def test_record_rejects_missing_lga_code_for_covers() -> None:
    bad = _covers_record()
    bad["lga_code"] = None
    with pytest.raises(ValidationError):
        AssetLgaAssignmentRecord.model_validate(bad)


def test_validate_accepts_unique_records() -> None:
    out = validate_lga_assignments(
        [_covers_record("VIC0001"), _fallback_record("VIC0002"), _unmatched_record("VIC0003")]
    )
    assert len(out) == 3


def test_validate_rejects_duplicate_asset_ids() -> None:
    with pytest.raises(ValueError, match="Duplicate asset_id"):
        validate_lga_assignments([_covers_record("VIC0001"), _covers_record("VIC0001")])


def test_validate_rejects_missing_lga_code_for_assigned_record() -> None:
    bad = _covers_record()
    bad["lga_code"] = None
    with pytest.raises(ValidationError):
        validate_lga_assignments([bad])


def test_validate_returns_empty_for_empty_input() -> None:
    assert validate_lga_assignments([]) == []


def test_persist_updates_only_matched_records() -> None:
    assignments = [
        _covers_record("VIC0001"),
        _intersects_record("VIC0002"),
        _fallback_record("VIC0003"),
        _unmatched_record("VIC0004"),
    ]
    session = FakeSession()
    n = persist_asset_lga_assignments(assignments, session, replace_existing=True)
    # 3 matched assignments → 3 returned; persistence is batched per LGA
    assert n == 3
    assert session.committed is True
    # Replace-existing path issues a clearing UPDATE first plus one UPDATE per LGA
    assert session.update_count() >= 2


def test_persist_replace_existing_clears_first() -> None:
    assignments = [_covers_record("VIC0001"), _fallback_record("VIC0002")]
    session = FakeSession()
    persist_asset_lga_assignments(assignments, session, replace_existing=True)
    # First UPDATE is the bulk-clear; remaining UPDATEs are per-lga writes
    update_statements = [s for s in session.executes if str(s).lower().startswith("update")]
    assert len(update_statements) >= 2
    assert session.committed is True


def test_persist_no_replace_existing_skips_already_set() -> None:
    assignments = [_covers_record("VIC0001"), _covers_record("VIC0002")]
    session = FakeSession(already_set_ids={"VIC0001"})
    n = persist_asset_lga_assignments(assignments, session, replace_existing=False)
    assert n == 1
    assert session.committed is True


def test_persist_validates_before_update() -> None:
    bad = _covers_record()
    bad["assignment_distance_km"] = 1.5  # invalid for covers
    session = FakeSession()
    with pytest.raises(ValidationError):
        persist_asset_lga_assignments([bad], session)
    assert session.committed is False


def test_persist_rolls_back_on_failure() -> None:
    assignments = [_covers_record("VIC0001")]

    class Boom(FakeSession):
        def execute(self, statement: Any, params: Any | None = None) -> _FakeResult:
            if str(statement).lower().startswith("update") and "lga_code = null" not in str(statement).lower():
                raise RuntimeError("boom")
            return super().execute(statement, params)

    session = Boom()
    with pytest.raises(RuntimeError):
        persist_asset_lga_assignments(assignments, session)
    assert session.rolled_back is True
    assert session.committed is False


def test_persist_returns_zero_for_empty_input() -> None:
    session = FakeSession()
    assert persist_asset_lga_assignments([], session) == 0
    assert session.committed is False


def test_persist_does_not_write_unmatched_records() -> None:
    assignments = [_unmatched_record("VIC0001"), _unmatched_record("VIC0002")]
    session = FakeSession()
    n = persist_asset_lga_assignments(assignments, session, replace_existing=True)
    assert n == 0
    # Replace-existing still issues the clearing UPDATE for the batch
    assert session.committed is True


def test_fetch_assignments_stamps_assigned_at() -> None:
    rows = [
        _FakeRow(
            asset_id="VIC0001",
            lga_code="LGA20660",
            lga_name="Melbourne",
            assignment_method="covers",
            assignment_distance_km=0.0,
        ),
        _FakeRow(
            asset_id="VIC0002",
            lga_code=None,
            lga_name=None,
            assignment_method="unmatched",
            assignment_distance_km=None,
        ),
    ]
    session = FakeSession(join_rows=rows)
    out = fetch_asset_lga_assignments(session)
    assert len(out) == 2
    assert all("assigned_at" in r for r in out)
    assert out[0]["assignment_method"] == "covers"
    assert out[0]["assignment_distance_km"] == 0.0
    assert out[1]["assignment_method"] == "unmatched"
    assert out[1]["assignment_distance_km"] is None


def test_run_returns_structured_summary() -> None:
    rows = [
        _FakeRow(
            asset_id="VIC0001",
            lga_code="LGA20660",
            lga_name="Melbourne",
            assignment_method="covers",
            assignment_distance_km=0.0,
        ),
        _FakeRow(
            asset_id="VIC0002",
            lga_code="LGA22750",
            lga_name="Greater Geelong",
            assignment_method="nearest_fallback",
            assignment_distance_km=4.5,
        ),
    ]
    session = FakeSession(n_assets=2, n_lgas=48, join_rows=rows)
    summary = run_asset_lga_assignment(session)
    AssetLgaAssignmentRunSummary.model_validate(summary)
    assert summary["assets_considered"] == 2
    assert summary["lga_boundaries_available"] == 48
    assert summary["assignments_generated"] == 2
    assert summary["covers_assignments"] == 1
    assert summary["nearest_fallback_assignments"] == 1
    assert summary["unmatched_assets"] == 0


def test_run_raises_when_no_assets() -> None:
    session = FakeSession(n_assets=0, n_lgas=48)
    with pytest.raises(ValueError, match="No assets"):
        run_asset_lga_assignment(session)


def test_run_raises_when_no_lgas() -> None:
    session = FakeSession(n_assets=5000, n_lgas=0)
    with pytest.raises(ValueError, match="No lga_boundaries"):
        run_asset_lga_assignment(session)


def test_run_subset_uses_subset_size_for_considered() -> None:
    rows = [
        _FakeRow(
            asset_id="VIC0001",
            lga_code="LGA20660",
            lga_name="Melbourne",
            assignment_method="covers",
            assignment_distance_km=0.0,
        ),
    ]
    session = FakeSession(n_assets=5000, n_lgas=48, join_rows=rows)
    summary = run_asset_lga_assignment(session, asset_ids=["VIC0001", "VIC9999"])
    assert summary["assets_considered"] == 2
    assert summary["assignments_generated"] == 1
