"""Tests for rainfall feature engineering: calculations, validation, persistence."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

import pytest
from pydantic import ValidationError

from src.db.models import RainfallFeature
from src.features.rainfall_features import (
    calculate_asset_rainfall_feature_record,
    calculate_percentile_rank,
    calculate_station_daily_statistics,
    calculate_station_rolling_3d_totals,
    calculate_trailing_rainfall_totals,
    persist_rainfall_features,
    run_rainfall_feature_generation,
    validate_rainfall_feature_records,
)
from src.schemas.rainfall_features import (
    RainfallFeatureRecord,
    RainfallFeatureRunSummary,
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
    def __init__(
        self,
        *,
        n_assets: int = 0,
        n_mappings: int = 0,
        join_rows: list[_FakeRow] | None = None,
        existing_pairs: set[tuple[str, date]] | None = None,
    ) -> None:
        self.executes: list[Any] = []
        self.added: list[Any] = []
        self.committed = False
        self.rolled_back = False
        self._n_assets = n_assets
        self._n_mappings = n_mappings
        self._join_rows = join_rows or []
        self._existing_pairs = set(existing_pairs or ())

    def execute(self, statement: Any, params: Any | None = None) -> _FakeResult:
        self.executes.append(statement)
        compiled = str(statement).lower()
        if compiled.startswith("delete"):
            return _FakeResult()
        if "from assets a" in compiled and "asset_station_mapping" in compiled:
            return _FakeResult(rows=self._join_rows)
        if "count(" in compiled and "from assets" in compiled:
            return _FakeResult(scalar_value=self._n_assets)
        if "count(" in compiled and "from asset_station_mapping" in compiled:
            return _FakeResult(scalar_value=self._n_mappings)
        if compiled.startswith("select") and "rainfall_features" in compiled:
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


def test_percentile_rank_uniform_distribution() -> None:
    dist = [0.0, 1.0, 2.0, 3.0, 4.0]
    assert calculate_percentile_rank(0.0, dist) == 0.2  # 1/5 <= 0
    assert calculate_percentile_rank(2.0, dist) == 0.6  # 3/5 <= 2
    assert calculate_percentile_rank(4.0, dist) == 1.0  # 5/5 <= 4


def test_percentile_rank_below_minimum() -> None:
    dist = [1.0, 2.0, 3.0]
    assert calculate_percentile_rank(0.5, dist) == 0.0  # nothing <= 0.5


def test_percentile_rank_all_identical_returns_1_when_equal() -> None:
    dist = [5.0] * 10
    assert calculate_percentile_rank(5.0, dist) == 1.0


def test_percentile_rank_all_identical_returns_0_when_below() -> None:
    dist = [5.0] * 10
    assert calculate_percentile_rank(4.0, dist) == 0.0


def test_percentile_rank_empty_distribution() -> None:
    assert calculate_percentile_rank(1.0, []) == 0.0


def test_percentile_rank_handles_duplicates_deterministically() -> None:
    dist = [0.0, 0.0, 5.0, 5.0, 5.0, 10.0, 10.0]
    # 5.0 <= values 5.0,5.0,5.0,10.0,10.0 - actually count items <= 5 is 5
    assert calculate_percentile_rank(5.0, dist) == 5 / 7


def test_station_statistics_p95_p99_max_days_above_p95() -> None:
    obs = [{"observation_date": date(2025, 1, 1) + timedelta(days=i), "rainfall_mm": float(i)} for i in range(100)]
    stats = calculate_station_daily_statistics(obs)
    # Linear-interp p95 of 0..99 equals 0 + 0.95*99 = 94.05
    assert stats["rainfall_p95_station"] == pytest.approx(94.05, abs=1e-6)
    assert stats["rainfall_p99_station"] == pytest.approx(98.01, abs=1e-6)
    assert stats["max_365d_rainfall_mm"] == 99.0
    # Days above p95 (>94.05): 95,96,97,98,99 -> 5 days
    assert stats["days_above_p95_365d"] == 5
    assert stats["observation_count"] == 100


def test_station_statistics_empty_returns_nones() -> None:
    stats = calculate_station_daily_statistics([])
    assert stats["rainfall_p95_station"] is None
    assert stats["rainfall_p99_station"] is None
    assert stats["max_365d_rainfall_mm"] is None
    assert stats["days_above_p95_365d"] is None


def test_trailing_totals_basic() -> None:
    obs = [
        {"observation_date": date(2025, 12, 31), "rainfall_mm": 10.0},
        {"observation_date": date(2025, 12, 30), "rainfall_mm": 5.0},
        {"observation_date": date(2025, 12, 29), "rainfall_mm": 3.0},
        {"observation_date": date(2025, 12, 28), "rainfall_mm": 2.0},
        {"observation_date": date(2025, 12, 25), "rainfall_mm": 100.0},  # outside 7d
        {"observation_date": date(2025, 12, 1), "rainfall_mm": 50.0},
    ]
    totals = calculate_trailing_rainfall_totals(obs, date(2025, 12, 31))
    assert totals["rainfall_1d_mm"] == 10.0
    assert totals["rainfall_3d_mm"] == 18.0  # 10 + 5 + 3
    # 7d window = Dec 25..31 inclusive. Sums 100 + 0 + 0 + 2 + 3 + 5 + 10 = 120
    assert totals["rainfall_7d_mm"] == 120.0
    # 30d window = Dec 2..31 inclusive (Dec 1 is outside)
    # Sums 100 + 2 + 3 + 5 + 10 = 120 (other days are zero)
    assert totals["rainfall_30d_mm"] == 120.0


def test_trailing_totals_treat_missing_as_zero() -> None:
    obs = [{"observation_date": date(2025, 12, 31), "rainfall_mm": 10.0}]
    totals = calculate_trailing_rainfall_totals(obs, date(2025, 12, 31))
    assert totals["rainfall_1d_mm"] == 10.0
    assert totals["rainfall_3d_mm"] == 10.0  # 10 + 0 + 0


def test_rolling_3d_totals_basic() -> None:
    base = date(2025, 1, 1)
    obs = [{"observation_date": base + timedelta(days=i), "rainfall_mm": float(i + 1)} for i in range(5)]
    rolling = calculate_station_rolling_3d_totals(obs)
    # Days 1..5: rainfall 1,2,3,4,5
    # Rolling 3d ending at day 3: 1+2+3=6; day 4: 2+3+4=9; day 5: 3+4+5=12
    assert len(rolling) == 3
    assert rolling[0]["rolling_3d_mm"] == 6.0
    assert rolling[1]["rolling_3d_mm"] == 9.0
    assert rolling[2]["rolling_3d_mm"] == 12.0


def test_rolling_3d_totals_skips_when_too_few_observations() -> None:
    obs = [{"observation_date": date(2025, 1, 1), "rainfall_mm": 1.0}]
    assert calculate_station_rolling_3d_totals(obs) == []


def test_rolling_3d_totals_skips_dates_with_gaps() -> None:
    obs = [
        {"observation_date": date(2025, 1, 1), "rainfall_mm": 1.0},
        {"observation_date": date(2025, 1, 2), "rainfall_mm": 2.0},
        # gap on 1/3
        {"observation_date": date(2025, 1, 4), "rainfall_mm": 4.0},
        {"observation_date": date(2025, 1, 5), "rainfall_mm": 5.0},
    ]
    rolling = calculate_station_rolling_3d_totals(obs)
    # Only 1/2 has both 12/31..1/2 (no, 2025-01 has no Dec data); not eligible
    # 1/4: needs 1/2 and 1/3. 1/3 missing -> skip
    # 1/5: needs 1/3 and 1/4. 1/3 missing -> skip
    assert rolling == []


def _year_obs(p95_target: float = 5.0) -> list[dict[str, Any]]:
    """Return 365 days of test observations with a known p95."""
    base = date(2025, 1, 1)
    out: list[dict[str, Any]] = []
    for i in range(365):
        # Most days dry; a few days hit p95-target
        if i % 20 == 0:
            value = p95_target
        elif i % 50 == 0:
            value = p95_target * 4
        else:
            value = 0.5
        out.append(
            {"observation_date": base + timedelta(days=i), "rainfall_mm": value}
        )
    return out


def test_feature_record_contains_all_canonical_fields() -> None:
    rec = calculate_asset_rainfall_feature_record(
        asset_id="VIC0001",
        station_id="086282",
        observations=_year_obs(),
        as_of_date=date(2025, 12, 31),
    )
    expected = {
        "asset_id",
        "station_id",
        "as_of_date",
        "rainfall_1d_mm",
        "rainfall_3d_mm",
        "rainfall_7d_mm",
        "rainfall_30d_mm",
        "rainfall_p95_station",
        "rainfall_p99_station",
        "rainfall_percentile",
        "max_365d_rainfall_mm",
        "days_above_p95_365d",
        "extreme_rainfall_flag",
    }
    assert set(rec.keys()) == expected


def test_feature_record_extreme_flag_true_when_3d_exceeds_3x_p95() -> None:
    base = date(2025, 1, 1)
    obs = []
    for i in range(365):
        obs.append({"observation_date": base + timedelta(days=i), "rainfall_mm": 1.0})
    # Make the trailing 3 days a heavy event well above 3 * p95(=1.0)
    obs[-1]["rainfall_mm"] = 50.0
    obs[-2]["rainfall_mm"] = 60.0
    obs[-3]["rainfall_mm"] = 70.0
    rec = calculate_asset_rainfall_feature_record(
        "VIC0001", "086282", obs, date(2025, 12, 31)
    )
    assert rec["rainfall_3d_mm"] == 180.0
    # p95 of mostly-1.0 with three giant tail days is ~1.0; 3d=180 > 3*1.0 = 3
    assert rec["extreme_rainfall_flag"] is True


def test_feature_record_extreme_flag_false_for_calm_year() -> None:
    base = date(2025, 1, 1)
    # Mild rain through year, but trailing 3 days are dry -> no extreme flag
    obs = [
        {
            "observation_date": base + timedelta(days=i),
            "rainfall_mm": 1.0 if i < 360 else 0.0,
        }
        for i in range(365)
    ]
    rec = calculate_asset_rainfall_feature_record(
        "VIC0001", "086282", obs, date(2025, 12, 31)
    )
    assert rec["rainfall_3d_mm"] == 0.0
    assert rec["extreme_rainfall_flag"] is False


def test_feature_record_extreme_flag_true_when_percentile_at_or_above_95() -> None:
    base = date(2025, 1, 1)
    obs = []
    for i in range(365):
        # Generate a varied series so rolling 3d distribution is non-degenerate
        obs.append({"observation_date": base + timedelta(days=i), "rainfall_mm": float(i % 7)})
    # End the year with a 3-day total above the 95th rolling percentile
    obs[-1]["rainfall_mm"] = 80.0
    obs[-2]["rainfall_mm"] = 80.0
    obs[-3]["rainfall_mm"] = 80.0
    rec = calculate_asset_rainfall_feature_record(
        "VIC0001", "086282", obs, date(2025, 12, 31)
    )
    assert rec["rainfall_percentile"] is not None
    assert rec["rainfall_percentile"] >= 0.95
    assert rec["extreme_rainfall_flag"] is True


def test_feature_record_raises_on_empty_observations() -> None:
    with pytest.raises(ValueError, match="No rainfall observations"):
        calculate_asset_rainfall_feature_record(
            "VIC0001", "086282", [], date(2025, 12, 31)
        )


def _good_record(
    asset_id: str = "VIC0001", as_of_date: date = date(2025, 12, 31)
) -> dict[str, Any]:
    return {
        "asset_id": asset_id,
        "station_id": "086282",
        "as_of_date": as_of_date,
        "rainfall_1d_mm": 5.0,
        "rainfall_3d_mm": 12.0,
        "rainfall_7d_mm": 30.0,
        "rainfall_30d_mm": 120.0,
        "rainfall_p95_station": 8.0,
        "rainfall_p99_station": 14.0,
        "rainfall_percentile": 0.85,
        "max_365d_rainfall_mm": 80.0,
        "days_above_p95_365d": 18,
        "extreme_rainfall_flag": False,
    }


def test_record_schema_validates_good_record() -> None:
    rec = RainfallFeatureRecord.model_validate(_good_record())
    assert rec.asset_id == "VIC0001"


def test_record_schema_rejects_negative_rainfall() -> None:
    bad = _good_record()
    bad["rainfall_3d_mm"] = -1.0
    with pytest.raises(ValidationError):
        RainfallFeatureRecord.model_validate(bad)


@pytest.mark.parametrize("p", [-0.01, 1.01, 2.0])
def test_record_schema_rejects_percentile_outside_unit_interval(p: float) -> None:
    bad = _good_record()
    bad["rainfall_percentile"] = p
    with pytest.raises(ValidationError):
        RainfallFeatureRecord.model_validate(bad)


def test_validate_accepts_unique_records() -> None:
    out = validate_rainfall_feature_records(
        [_good_record("VIC0001"), _good_record("VIC0002")]
    )
    assert len(out) == 2


def test_validate_rejects_duplicate_asset_date() -> None:
    with pytest.raises(ValueError, match="Duplicate"):
        validate_rainfall_feature_records(
            [_good_record("VIC0001"), _good_record("VIC0001")]
        )


def test_persist_inserts_when_replace_existing_true() -> None:
    records = [_good_record("VIC0001"), _good_record("VIC0002")]
    session = FakeSession()
    n = persist_rainfall_features(records, session, replace_existing=True)
    assert n == 2
    assert all(isinstance(o, RainfallFeature) for o in session.added)
    assert session.committed is True


def test_persist_replace_existing_issues_delete_first() -> None:
    records = [_good_record("VIC0001"), _good_record("VIC0002")]
    session = FakeSession()
    persist_rainfall_features(records, session, replace_existing=True)
    deletes = [s for s in session.executes if str(s).lower().startswith("delete")]
    assert len(deletes) == 1


def test_persist_skips_existing_when_replace_existing_false() -> None:
    records = [_good_record("VIC0001"), _good_record("VIC0002")]
    session = FakeSession(existing_pairs={("VIC0001", date(2025, 12, 31))})
    n = persist_rainfall_features(records, session, replace_existing=False)
    assert n == 1
    assert {a.asset_id for a in session.added} == {"VIC0002"}


def test_persist_validates_before_insert() -> None:
    bad = _good_record()
    bad["rainfall_3d_mm"] = -5.0
    session = FakeSession()
    with pytest.raises(ValidationError):
        persist_rainfall_features([bad], session)
    assert session.committed is False


def test_persist_rolls_back_on_failure() -> None:
    records = [_good_record("VIC0001")]

    class Boom(FakeSession):
        def add_all(self, objs: list[Any]) -> None:
            raise RuntimeError("boom")

    session = Boom()
    with pytest.raises(RuntimeError):
        persist_rainfall_features(records, session)
    assert session.rolled_back is True
    assert session.committed is False


def test_persist_returns_zero_for_empty_input() -> None:
    session = FakeSession()
    assert persist_rainfall_features([], session) == 0
    assert session.committed is False


def test_run_returns_structured_summary() -> None:
    base = date(2025, 1, 1)
    rows: list[_FakeRow] = []
    for i in range(365):
        rows.append(
            _FakeRow(
                asset_id="VIC0001",
                station_id="086282",
                observation_date=base + timedelta(days=i),
                rainfall_mm=1.0,
                postcode="Richmond",
                lga_code="LGA20660",
                station_name="Melbourne Olympic Park",
                station_distance_km=4.5,
                station_confidence_weight=0.955,
            )
        )
    session = FakeSession(n_assets=1, n_mappings=1, join_rows=rows)
    summary = run_rainfall_feature_generation(session, as_of_date=date(2025, 12, 31))
    RainfallFeatureRunSummary.model_validate(summary)
    assert summary["assets_considered"] == 1
    assert summary["mapped_assets"] == 1
    assert summary["stations_used"] == 1
    assert summary["feature_records_generated"] == 1
    assert summary["feature_records_inserted"] == 1
    assert summary["lookback_start_date"] == date(2025, 1, 1)
    assert summary["lookback_end_date"] == date(2025, 12, 31)


def test_run_raises_when_no_assets() -> None:
    session = FakeSession(n_assets=0, n_mappings=1)
    with pytest.raises(ValueError, match="No assets"):
        run_rainfall_feature_generation(session)


def test_run_raises_when_no_mappings() -> None:
    session = FakeSession(n_assets=5000, n_mappings=0)
    with pytest.raises(ValueError, match="asset_station_mapping"):
        run_rainfall_feature_generation(session)
