"""Tests for rule-based risk scoring: components, formula, validation, persistence"""

from __future__ import annotations

from datetime import date
from typing import Any

import pytest
from pydantic import ValidationError

from src.db.models import AssetRiskScore
from src.risk.scoring import (
    EXPOSURE_WEIGHT_MAX,
    EXPOSURE_WEIGHT_MIN,
    VULNERABILITY_WEIGHT_MAX,
    VULNERABILITY_WEIGHT_MIN,
    calculate_asset_risk_score_record,
    calculate_exposure_weight,
    calculate_rainfall_extreme_score,
    calculate_raw_risk_score,
    calculate_vulnerability_weight,
    clip_risk_score,
    persist_asset_risk_scores,
    validate_asset_risk_score_records,
)
from src.schemas.risk import AssetRiskScoreRecord


class _FakeResult:
    def __init__(self, rows: list[Any] | None = None, scalar_value: Any = None) -> None:
        self._rows = rows or []
        self._scalar = scalar_value

    def all(self) -> list[Any]:
        return self._rows

    def scalar(self) -> Any:
        return self._scalar


class FakeSession:
    def __init__(self, *, existing_pairs: set[tuple[str, date]] | None = None) -> None:
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
        if compiled.startswith("select") and "asset_risk_scores" in compiled:
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


def test_extreme_score_bounded_to_unit_interval_times_100() -> None:
    assert (
        0.0
        <= calculate_rainfall_extreme_score(
            rainfall_3d_mm=0.0,
            rainfall_percentile=0.0,
            rainfall_p95_station=5.0,
            rainfall_p99_station=15.0,
            extreme_rainfall_flag=False,
        )
        <= 100.0
    )
    assert (
        calculate_rainfall_extreme_score(
            rainfall_3d_mm=1000.0,
            rainfall_percentile=1.0,
            rainfall_p95_station=5.0,
            rainfall_p99_station=15.0,
            extreme_rainfall_flag=True,
        )
        == 100.0
    )


def test_extreme_score_monotonic_in_percentile() -> None:
    scores = [
        calculate_rainfall_extreme_score(
            rainfall_3d_mm=10.0,
            rainfall_percentile=p,
            rainfall_p95_station=8.0,
            rainfall_p99_station=14.0,
            extreme_rainfall_flag=False,
        )
        for p in (0.0, 0.1, 0.3, 0.6, 0.9, 1.0)
    ]
    assert scores == sorted(scores)


def test_extreme_score_at_least_85_when_extreme_flag_true() -> None:
    score = calculate_rainfall_extreme_score(
        rainfall_3d_mm=2.0,
        rainfall_percentile=0.20,
        rainfall_p95_station=8.0,
        rainfall_p99_station=14.0,
        extreme_rainfall_flag=True,
    )
    assert score >= 85.0


def test_extreme_score_close_to_100_when_3d_above_3x_p99() -> None:
    score = calculate_rainfall_extreme_score(
        rainfall_3d_mm=60.0,
        rainfall_percentile=0.95,
        rainfall_p95_station=8.0,
        rainfall_p99_station=15.0,
        extreme_rainfall_flag=False,
    )
    # 60 >= 3 * p99 (45) → score floor of 99
    assert score >= 99.0


def test_extreme_score_at_least_90_when_3d_above_3x_p95() -> None:
    score = calculate_rainfall_extreme_score(
        rainfall_3d_mm=30.0,
        rainfall_percentile=0.10,
        rainfall_p95_station=8.0,
        rainfall_p99_station=20.0,
        extreme_rainfall_flag=False,
    )
    # 30 >= 3 * p95 (24) but < 3 * p99 (60) → at least 90, less than 99
    assert score >= 90.0


def test_extreme_score_uses_fallback_ratio_when_percentile_missing() -> None:
    score = calculate_rainfall_extreme_score(
        rainfall_3d_mm=24.0,
        rainfall_percentile=None,
        rainfall_p95_station=8.0,
        rainfall_p99_station=None,
        extreme_rainfall_flag=False,
    )
    # ratio = 24 / 24 = 1.0 → base 100; and 3*p95 hit → score >= 90
    assert score >= 90.0


def test_extreme_score_zero_when_no_rainfall_signal() -> None:
    score = calculate_rainfall_extreme_score(
        rainfall_3d_mm=0.0,
        rainfall_percentile=None,
        rainfall_p95_station=None,
        rainfall_p99_station=None,
        extreme_rainfall_flag=False,
    )
    assert score == 0.0


def test_exposure_weight_within_canonical_range() -> None:
    w = calculate_exposure_weight(
        asset_value=1_000_000,
        coverage_limit=100_000,
    )
    assert EXPOSURE_WEIGHT_MIN <= w <= EXPOSURE_WEIGHT_MAX


def test_exposure_weight_uses_portfolio_context_when_provided() -> None:
    portfolio_av = [1e5, 5e5, 1e6, 5e6, 1e7]
    portfolio_cl = [1e4, 5e4, 1e5, 5e5, 1e6]
    low = calculate_exposure_weight(
        1e5, 1e4, portfolio_asset_values=portfolio_av, portfolio_coverage_limits=portfolio_cl
    )
    high = calculate_exposure_weight(
        1e7, 1e6, portfolio_asset_values=portfolio_av, portfolio_coverage_limits=portfolio_cl
    )
    assert high > low
    assert EXPOSURE_WEIGHT_MIN <= low <= EXPOSURE_WEIGHT_MAX
    assert EXPOSURE_WEIGHT_MIN <= high <= EXPOSURE_WEIGHT_MAX


def test_exposure_weight_increases_with_asset_value_in_fallback_path() -> None:
    low = calculate_exposure_weight(asset_value=200_000, coverage_limit=20_000)
    high = calculate_exposure_weight(asset_value=10_000_000, coverage_limit=500_000)
    assert high >= low


def test_exposure_weight_rejects_non_positive_inputs() -> None:
    with pytest.raises(ValueError):
        calculate_exposure_weight(asset_value=0, coverage_limit=10)
    with pytest.raises(ValueError):
        calculate_exposure_weight(asset_value=10, coverage_limit=0)


def test_vulnerability_weight_within_canonical_range() -> None:
    for industry in (
        "hospitality",
        "tourism",
        "professional_services",
        "technology",
        "unknown_industry",
    ):
        w = calculate_vulnerability_weight(industry)
        assert VULNERABILITY_WEIGHT_MIN <= w <= VULNERABILITY_WEIGHT_MAX


def test_high_vulnerability_industries_score_above_neutral() -> None:
    for industry in ("tourism", "logistics", "storage", "hospitality"):
        assert calculate_vulnerability_weight(industry) > 1.0


def test_low_vulnerability_industries_score_at_or_below_neutral() -> None:
    for industry in ("professional_services", "technology"):
        assert calculate_vulnerability_weight(industry) <= 1.0


def test_business_type_modifier_adjusts_baseline() -> None:
    base = calculate_vulnerability_weight("storage")
    bumped = calculate_vulnerability_weight("storage", business_type="cold_storage")
    assert bumped >= base
    base = calculate_vulnerability_weight("professional_services")
    discounted = calculate_vulnerability_weight(
        "professional_services", business_type="office"
    )
    assert discounted <= base


def test_unknown_industry_returns_neutral() -> None:
    w = calculate_vulnerability_weight("space_tourism")
    assert w == 1.0


def test_raw_score_uses_exact_multiplication() -> None:
    raw = calculate_raw_risk_score(80.0, 1.2, 1.3, 0.95)
    assert raw == 80.0 * 1.2 * 1.3 * 0.95


def test_clip_risk_score_below_zero() -> None:
    assert clip_risk_score(-10.0) == 0.0


def test_clip_risk_score_above_100() -> None:
    assert clip_risk_score(150.0) == 100.0


def test_clip_risk_score_in_range_passes_through() -> None:
    assert clip_risk_score(42.5) == 42.5


def _asset() -> dict[str, Any]:
    return {
        "asset_id": "VIC0001",
        "business_type": "warehouse",
        "industry": "logistics",
        "asset_value": 1_500_000.0,
        "coverage_limit": 200_000.0,
    }


def _features(percentile: float = 0.6, extreme: bool = False) -> dict[str, Any]:
    return {
        "as_of_date": date(2025, 12, 31),
        "rainfall_3d_mm": 12.0,
        "rainfall_p95_station": 7.5,
        "rainfall_p99_station": 14.0,
        "rainfall_percentile": percentile,
        "extreme_rainfall_flag": extreme,
    }


def _mapping(weight: float = 0.95) -> dict[str, Any]:
    return {"station_confidence_weight": weight}


def test_record_contains_all_canonical_fields() -> None:
    rec = calculate_asset_risk_score_record(_asset(), _features(), _mapping())
    expected = {
        "asset_id",
        "as_of_date",
        "rainfall_extreme_score",
        "exposure_weight",
        "vulnerability_weight",
        "station_confidence_weight",
        "raw_score",
        "risk_score",
        "risk_band",
    }
    assert set(rec.keys()) == expected


def test_record_risk_score_is_clipped_to_unit_interval_times_100() -> None:
    rec = calculate_asset_risk_score_record(
        _asset(), _features(percentile=1.0, extreme=True), _mapping(weight=1.0)
    )
    assert 0.0 <= rec["risk_score"] <= 100.0


def test_record_risk_band_matches_score() -> None:
    rec = calculate_asset_risk_score_record(_asset(), _features(percentile=0.1), _mapping())
    if rec["risk_score"] < 25:
        assert rec["risk_band"] == "Low"
    elif rec["risk_score"] < 50:
        assert rec["risk_band"] == "Medium"
    elif rec["risk_score"] < 75:
        assert rec["risk_band"] == "High"
    else:
        assert rec["risk_band"] == "Severe"


def test_record_rejects_invalid_station_confidence() -> None:
    with pytest.raises(ValueError):
        calculate_asset_risk_score_record(
            _asset(), _features(), {"station_confidence_weight": 0.10}
        )


def _good_record(asset_id: str = "VIC0001") -> dict[str, Any]:
    return {
        "asset_id": asset_id,
        "as_of_date": date(2025, 12, 31),
        "rainfall_extreme_score": 60.0,
        "exposure_weight": 1.05,
        "vulnerability_weight": 1.20,
        "station_confidence_weight": 0.95,
        "raw_score": 60.0 * 1.05 * 1.20 * 0.95,
        "risk_score": 71.82,
        "risk_band": "High",
    }


def test_record_schema_validates_good_record() -> None:
    rec = AssetRiskScoreRecord.model_validate(_good_record())
    assert rec.risk_band == "High"


@pytest.mark.parametrize(
    "field, value",
    [
        ("rainfall_extreme_score", -1),
        ("rainfall_extreme_score", 101),
        ("exposure_weight", 0.5),
        ("exposure_weight", 1.5),
        ("vulnerability_weight", 0.5),
        ("vulnerability_weight", 1.6),
        ("station_confidence_weight", 0.4),
        ("station_confidence_weight", 1.1),
        ("risk_score", -1),
        ("risk_score", 101),
        ("risk_band", "Critical"),
    ],
)
def test_record_schema_rejects_invalid_component_ranges(field: str, value: Any) -> None:
    bad = _good_record()
    bad[field] = value
    with pytest.raises(ValidationError):
        AssetRiskScoreRecord.model_validate(bad)


def test_validate_accepts_unique_records() -> None:
    out = validate_asset_risk_score_records(
        [_good_record("VIC0001"), _good_record("VIC0002")]
    )
    assert len(out) == 2


def test_validate_rejects_duplicate_asset_date() -> None:
    with pytest.raises(ValueError, match="Duplicate"):
        validate_asset_risk_score_records(
            [_good_record("VIC0001"), _good_record("VIC0001")]
        )


def test_persist_inserts_when_replace_existing_true() -> None:
    records = [_good_record("VIC0001"), _good_record("VIC0002")]
    session = FakeSession()
    n = persist_asset_risk_scores(records, session, replace_existing=True)
    assert n == 2
    assert all(isinstance(o, AssetRiskScore) for o in session.added)
    assert session.committed is True


def test_persist_replace_existing_issues_delete_first() -> None:
    records = [_good_record("VIC0001")]
    session = FakeSession()
    persist_asset_risk_scores(records, session, replace_existing=True)
    deletes = [s for s in session.executes if str(s).lower().startswith("delete")]
    assert len(deletes) == 1


def test_persist_skips_existing_when_replace_existing_false() -> None:
    records = [_good_record("VIC0001"), _good_record("VIC0002")]
    session = FakeSession(existing_pairs={("VIC0001", date(2025, 12, 31))})
    n = persist_asset_risk_scores(records, session, replace_existing=False)
    assert n == 1
    assert {o.asset_id for o in session.added} == {"VIC0002"}


def test_persist_validates_before_insert() -> None:
    bad = _good_record()
    bad["risk_score"] = 200.0
    session = FakeSession()
    with pytest.raises(ValidationError):
        persist_asset_risk_scores([bad], session)
    assert session.committed is False


def test_persist_rolls_back_on_failure() -> None:
    records = [_good_record("VIC0001")]

    class Boom(FakeSession):
        def add_all(self, objs: list[Any]) -> None:
            raise RuntimeError("boom")

    session = Boom()
    with pytest.raises(RuntimeError):
        persist_asset_risk_scores(records, session)
    assert session.rolled_back is True
    assert session.committed is False


def test_persist_returns_zero_for_empty_input() -> None:
    session = FakeSession()
    assert persist_asset_risk_scores([], session) == 0
    assert session.committed is False
