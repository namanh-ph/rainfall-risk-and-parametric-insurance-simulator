"""Tests for confidence calculation, validation, and persistence"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from pydantic import ValidationError

from src.db.models import AssetStationMapping
from src.geospatial.station_matching import (
    calculate_station_confidence_weight,
    fetch_nearest_station_matches,
    replace_asset_station_mappings,
    run_asset_station_matching,
    validate_station_matches,
)
from src.schemas.station_matching import StationMatchingRunSummary, StationMatchRecord


class _FakeRow:
    """Minimal row-like object with mapping access"""

    def __init__(self, **kwargs: Any) -> None:
        self._data = kwargs

    @property
    def _mapping(self) -> dict[str, Any]:
        return self._data


class _FakeResult:
    def __init__(
        self,
        rows: list[Any] | None = None,
        scalar_value: Any = None,
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
    """SQLAlchemy session double"""

    def __init__(
        self,
        *,
        existing_asset_ids: set[str] | None = None,
        n_assets: int = 0,
        n_stations: int = 0,
        match_rows: list[_FakeRow] | None = None,
    ) -> None:
        self.added: list[Any] = []
        self.committed = False
        self.rolled_back = False
        self.deletes: list[Any] = []
        self._existing_asset_ids = set(existing_asset_ids or ())
        self._n_assets = n_assets
        self._n_stations = n_stations
        self._match_rows = match_rows or []
        self._select_calls = 0

    def execute(self, statement: Any, params: Any | None = None) -> _FakeResult:
        compiled = str(statement).lower()
        if compiled.startswith("delete"):
            self.deletes.append(statement)
            return _FakeResult()
        # nearest-station query (TextClause from build_nearest_station_query)
        if "lateral" in compiled and "st_distance" in compiled:
            return _FakeResult(rows=self._match_rows)
        # SELECT count(*) FROM ...; order matters: assets queried first
        if "count(" in compiled and "from assets" in compiled:
            return _FakeResult(scalar_value=self._n_assets)
        if "count(" in compiled and "from rainfall_stations" in compiled:
            return _FakeResult(scalar_value=self._n_stations)
        # Fallback: existing-id select
        if compiled.startswith("select"):
            return _FakeResult(rows=[(aid,) for aid in self._existing_asset_ids])
        return _FakeResult()

    def add_all(self, objs: list[Any]) -> None:
        self.added.extend(objs)

    def commit(self) -> None:
        self.committed = True

    def rollback(self) -> None:
        self.rolled_back = True

    def close(self) -> None:  # pragma: no cover
        pass


def test_confidence_returns_1_for_zero_distance() -> None:
    assert calculate_station_confidence_weight(0.0) == 1.0


def test_confidence_returns_0_936_for_6_4_km() -> None:
    assert calculate_station_confidence_weight(6.4) == pytest.approx(0.936, abs=1e-9)


def test_confidence_returns_floor_for_50_km() -> None:
    assert calculate_station_confidence_weight(50.0) == 0.5


def test_confidence_returns_floor_for_120_km() -> None:
    assert calculate_station_confidence_weight(120.0) == 0.5


def test_confidence_rejects_negative_distance() -> None:
    with pytest.raises(ValueError, match="non-negative"):
        calculate_station_confidence_weight(-0.001)


def test_confidence_clip_floor_is_50() -> None:
    # Exactly the boundary case 1 - 50/100 = 0.5; equal to the floor
    assert calculate_station_confidence_weight(49.9999) > 0.5
    assert calculate_station_confidence_weight(50.0) == 0.5
    assert calculate_station_confidence_weight(51.0) == 0.5  # clipped


def test_station_match_record_validates_valid_match() -> None:
    rec = StationMatchRecord.model_validate(
        {
            "asset_id": "VIC0001",
            "station_id": "086282",
            "station_distance_km": 4.5,
            "station_confidence_weight": 0.955,
            "matched_at": datetime.now(UTC),
        }
    )
    assert rec.asset_id == "VIC0001"


@pytest.mark.parametrize("weight", [-0.1, 0.49, 1.01, 2.0])
def test_station_match_record_rejects_invalid_confidence(weight: float) -> None:
    with pytest.raises(ValidationError):
        StationMatchRecord.model_validate(
            {
                "asset_id": "VIC0001",
                "station_id": "086282",
                "station_distance_km": 4.5,
                "station_confidence_weight": weight,
                "matched_at": datetime.now(UTC),
            }
        )


def test_station_match_record_rejects_negative_distance() -> None:
    with pytest.raises(ValidationError):
        StationMatchRecord.model_validate(
            {
                "asset_id": "VIC0001",
                "station_id": "086282",
                "station_distance_km": -1.0,
                "station_confidence_weight": 0.99,
                "matched_at": datetime.now(UTC),
            }
        )


def _good_match(asset_id: str, distance: float = 4.5) -> dict[str, Any]:
    return {
        "asset_id": asset_id,
        "station_id": "086282",
        "station_distance_km": distance,
        "station_confidence_weight": calculate_station_confidence_weight(distance),
        "matched_at": datetime.now(UTC),
    }


def test_validate_accepts_unique_matches() -> None:
    out = validate_station_matches([_good_match("VIC0001"), _good_match("VIC0002")])
    assert len(out) == 2


def test_validate_rejects_duplicate_asset_ids() -> None:
    with pytest.raises(ValueError, match="Duplicate asset_id"):
        validate_station_matches([_good_match("VIC0001"), _good_match("VIC0001")])


def test_validate_rejects_negative_distance() -> None:
    bad = _good_match("VIC0001")
    bad["station_distance_km"] = -1.0
    with pytest.raises(ValidationError):
        validate_station_matches([bad])


def test_validate_returns_empty_for_empty_input() -> None:
    assert validate_station_matches([]) == []


def test_replace_inserts_all_when_replace_existing_true() -> None:
    matches = [_good_match("VIC0001"), _good_match("VIC0002")]
    session = FakeSession()
    n = replace_asset_station_mappings(matches, session, replace_existing=True)
    assert n == 2
    assert len(session.deletes) == 1  # always issues a DELETE for the batch
    assert session.committed is True
    assert all(isinstance(o, AssetStationMapping) for o in session.added)


def test_replace_skips_existing_when_replace_existing_false() -> None:
    matches = [_good_match("VIC0001"), _good_match("VIC0002"), _good_match("VIC0003")]
    session = FakeSession(existing_asset_ids={"VIC0002"})
    n = replace_asset_station_mappings(matches, session, replace_existing=False)
    assert n == 2
    assert {a.asset_id for a in session.added} == {"VIC0001", "VIC0003"}
    assert session.committed is True
    assert session.deletes == []


def test_replace_validates_before_insertion() -> None:
    bad = _good_match("VIC0001")
    bad["station_confidence_weight"] = 0.0  # below floor
    session = FakeSession()
    with pytest.raises(ValidationError):
        replace_asset_station_mappings([bad], session)
    assert session.committed is False
    assert session.added == []


def test_replace_rolls_back_on_failure() -> None:
    matches = [_good_match("VIC0001")]

    class Boom(FakeSession):
        def add_all(self, objs: list[Any]) -> None:
            raise RuntimeError("boom")

    session = Boom()
    with pytest.raises(RuntimeError):
        replace_asset_station_mappings(matches, session)
    assert session.rolled_back is True
    assert session.committed is False


def test_replace_returns_zero_for_empty_input() -> None:
    session = FakeSession()
    assert replace_asset_station_mappings([], session) == 0
    assert session.committed is False


def test_fetch_nearest_station_matches_augments_with_confidence_and_matched_at() -> None:
    rows = [
        _FakeRow(asset_id="VIC0001", station_id="086282", station_distance_km=0.0),
        _FakeRow(asset_id="VIC0002", station_id="086282", station_distance_km=6.4),
        _FakeRow(asset_id="VIC0003", station_id="086282", station_distance_km=120.0),
    ]
    session = FakeSession(match_rows=rows)
    matches = fetch_nearest_station_matches(session)
    assert len(matches) == 3
    assert matches[0]["station_confidence_weight"] == 1.0
    assert matches[1]["station_confidence_weight"] == pytest.approx(0.936, abs=1e-9)
    assert matches[2]["station_confidence_weight"] == 0.5
    assert all("matched_at" in m for m in matches)


def test_run_asset_station_matching_returns_structured_summary() -> None:
    rows = [_FakeRow(asset_id="VIC0001", station_id="086282", station_distance_km=2.0)]
    session = FakeSession(n_assets=1, n_stations=15, match_rows=rows)
    summary = run_asset_station_matching(session)
    StationMatchingRunSummary.model_validate(summary)
    assert summary["assets_considered"] == 1
    assert summary["stations_available"] == 15
    assert summary["matches_generated"] == 1
    assert summary["mappings_inserted"] == 1
    assert summary["unmatched_assets"] == 0
    assert summary["max_distance_km"] is None
    assert summary["replace_existing"] is True


def test_run_asset_station_matching_subset_uses_subset_size() -> None:
    rows = [_FakeRow(asset_id="VIC0001", station_id="086282", station_distance_km=2.0)]
    session = FakeSession(n_assets=5000, n_stations=15, match_rows=rows)
    summary = run_asset_station_matching(session, asset_ids=["VIC0001", "VIC9999"])
    assert summary["assets_considered"] == 2
    assert summary["matches_generated"] == 1
    assert summary["unmatched_assets"] == 1


def test_run_asset_station_matching_raises_when_no_assets() -> None:
    session = FakeSession(n_assets=0, n_stations=15)
    with pytest.raises(ValueError, match="No assets"):
        run_asset_station_matching(session)


def test_run_asset_station_matching_raises_when_no_stations() -> None:
    session = FakeSession(n_assets=5000, n_stations=0)
    with pytest.raises(ValueError, match="No rainfall stations"):
        run_asset_station_matching(session)
