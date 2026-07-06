"""Tests for ML training dataset construction primitives"""

from __future__ import annotations

import json
from datetime import date
from typing import Any

import pytest
from pydantic import ValidationError

from src.db.models import ModelTrainingData
from src.ml.dataset import (
    DEFAULT_FEATURE_VERSION,
    build_category_encoders,
    build_engineered_feature_payload,
    build_model_training_record,
    calculate_ratio,
    derive_target_extreme_rainfall_event,
    encode_category,
    persist_model_training_data,
    safe_log1p,
    validate_model_training_records,
)
from src.schemas.ml_dataset import ModelTrainingRecord


class _FakeResult:
    def __init__(self, rows: list[Any] | None = None) -> None:
        self._rows = rows or []

    def all(self) -> list[Any]:
        return self._rows


class FakeSession:
    def __init__(
        self,
        *,
        existing_keys: set[tuple[str, date, str]] | None = None,
    ) -> None:
        self.executes: list[Any] = []
        self.added: list[Any] = []
        self.committed = False
        self.rolled_back = False
        self._existing_keys = set(existing_keys or ())

    def execute(self, statement: Any, params: Any | None = None) -> _FakeResult:
        self.executes.append(statement)
        compiled = str(statement).lower()
        if compiled.startswith("delete"):
            return _FakeResult()
        if compiled.startswith("select") and "model_training_data" in compiled:
            return _FakeResult(rows=list(self._existing_keys))
        return _FakeResult()

    def add_all(self, objs: list[Any]) -> None:
        self.added.extend(objs)

    def commit(self) -> None:
        self.committed = True

    def rollback(self) -> None:
        self.rolled_back = True

    def close(self) -> None:  # pragma: no cover
        pass


def test_safe_log1p_positive_returns_log1p() -> None:
    assert safe_log1p(0) == 0.0
    assert safe_log1p(1) == pytest.approx(0.6931471805599453, abs=1e-9)
    assert safe_log1p(1e6) > 13


def test_safe_log1p_handles_null_and_invalid() -> None:
    assert safe_log1p(None) is None
    assert safe_log1p("not_a_number") is None
    assert safe_log1p(-1.0) is None
    assert safe_log1p(float("inf")) is None
    assert safe_log1p(float("nan")) is None


def test_calculate_ratio_normal() -> None:
    assert calculate_ratio(50, 100) == 0.5


def test_calculate_ratio_zero_denominator_returns_none() -> None:
    assert calculate_ratio(50, 0) is None


def test_calculate_ratio_null_cases() -> None:
    assert calculate_ratio(None, 1) is None
    assert calculate_ratio(1, None) is None
    assert calculate_ratio(None, None) is None


def test_build_category_encoders_is_deterministic() -> None:
    rows = [
        {"industry": "retail", "business_type": "shop"},
        {"industry": "hospitality", "business_type": "cafe"},
        {"industry": "retail", "business_type": "shop"},
    ]
    encoders = build_category_encoders(rows)
    assert encoders["industry"]["__unknown__"] == 0
    # Sorted lex: hospitality, retail
    assert encoders["industry"]["hospitality"] == 1
    assert encoders["industry"]["retail"] == 2


def test_encode_category_maps_unknown_to_zero() -> None:
    encoders = build_category_encoders([{"industry": "retail"}])
    assert encode_category(None, encoders["industry"]) == 0
    assert encode_category("", encoders["industry"]) == 0
    assert encode_category("never_seen", encoders["industry"]) == 0
    assert encode_category("retail", encoders["industry"]) == 1


def test_target_true_when_extreme_flag() -> None:
    row = {"extreme_rainfall_flag": True, "rainfall_percentile": 0.1, "rainfall_3d_mm": 1, "rainfall_p95_station": 100}
    assert derive_target_extreme_rainfall_event(row) is True


def test_target_true_when_percentile_above_95() -> None:
    row = {"extreme_rainfall_flag": False, "rainfall_percentile": 0.96, "rainfall_3d_mm": 1, "rainfall_p95_station": 100}
    assert derive_target_extreme_rainfall_event(row) is True


def test_target_true_when_3d_above_3x_p95() -> None:
    row = {
        "extreme_rainfall_flag": False,
        "rainfall_percentile": 0.1,
        "rainfall_3d_mm": 50.0,
        "rainfall_p95_station": 10.0,
    }
    assert derive_target_extreme_rainfall_event(row) is True


def test_target_false_for_calm_inputs() -> None:
    row = {
        "extreme_rainfall_flag": False,
        "rainfall_percentile": 0.5,
        "rainfall_3d_mm": 5.0,
        "rainfall_p95_station": 10.0,
    }
    assert derive_target_extreme_rainfall_event(row) is False


def test_target_robust_when_p95_null() -> None:
    row = {
        "extreme_rainfall_flag": False,
        "rainfall_percentile": 0.5,
        "rainfall_3d_mm": 5.0,
        "rainfall_p95_station": None,
    }
    assert derive_target_extreme_rainfall_event(row) is False


def test_target_does_not_depend_on_payout_or_risk_score() -> None:
    row = {
        "extreme_rainfall_flag": False,
        "rainfall_percentile": 0.5,
        "rainfall_3d_mm": 5.0,
        "rainfall_p95_station": 10.0,
        "baseline_payout_rate": 1.0,
        "risk_score": 99.0,
    }
    assert derive_target_extreme_rainfall_event(row) is False


def _input_row(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "asset_id": "VIC0001",
        "as_of_date": date(2025, 12, 31),
        "business_type": "warehouse",
        "industry": "logistics",
        "postcode": "Dandenong",
        "latitude": -37.99,
        "longitude": 145.21,
        "asset_value": 1_500_000,
        "annual_revenue": 800_000,
        "coverage_limit": 250_000,
        "lga_code": "LGA21890c",
        "lga_name": "Greater Dandenong",
        "station_id": "086282",
        "station_distance_km": 8.5,
        "station_confidence_weight": 0.92,
        "rainfall_1d_mm": 1.2,
        "rainfall_3d_mm": 18.5,
        "rainfall_7d_mm": 25.0,
        "rainfall_30d_mm": 110.0,
        "rainfall_p95_station": 7.5,
        "rainfall_p99_station": 14.0,
        "rainfall_percentile": 0.85,
        "max_365d_rainfall_mm": 85.0,
        "days_above_p95_365d": 19,
        "extreme_rainfall_flag": False,
        "rainfall_extreme_score": 85.0,
        "exposure_weight": 1.1,
        "vulnerability_weight": 1.25,
        "raw_score": 116.875,
        "risk_score": 100.0,
        "risk_band": "Severe",
        "baseline_payout_rate": 0.0,
        "baseline_trigger_status": "not_triggered",
        "baseline_estimated_payout": 0.0,
        "sensitive_threshold_payout_rate": 0.2,
        "sensitive_threshold_estimated_payout": 50_000.0,
        "very_sensitive_threshold_payout_rate": 1.0,
        "very_sensitive_threshold_estimated_payout": 250_000.0,
    }
    base.update(overrides)
    return base


def test_feature_payload_includes_required_key_groups() -> None:
    row = _input_row()
    encoders = build_category_encoders([row])
    payload = build_engineered_feature_payload(row, encoders)
    required_keys = {
        "asset_value", "coverage_limit", "annual_revenue",
        "log_asset_value", "log_coverage_limit", "log_annual_revenue",
        "coverage_to_asset_value_ratio", "coverage_to_revenue_ratio",
        "industry", "business_type", "postcode", "lga_code", "lga_name",
        "industry_code", "business_type_code", "postcode_code", "lga_code_encoded",
        "latitude", "longitude",
        "station_id", "station_distance_km", "station_confidence_weight",
        "has_lga_assignment",
        "rainfall_1d_mm", "rainfall_3d_mm", "rainfall_7d_mm", "rainfall_30d_mm",
        "rainfall_p95_station", "rainfall_p99_station", "rainfall_percentile",
        "max_365d_rainfall_mm", "days_above_p95_365d", "extreme_rainfall_flag",
        "rainfall_3d_to_p95_ratio", "rainfall_3d_to_p99_ratio", "rainfall_30d_to_p95_ratio",
        "rainfall_extreme_score", "exposure_weight", "vulnerability_weight",
        "raw_score", "risk_score", "risk_band", "risk_band_code",
        "baseline_payout_rate", "baseline_trigger_status",
        "baseline_estimated_payout", "baseline_triggered_flag",
        "sensitive_threshold_triggered_flag",
        "very_sensitive_threshold_triggered_flag",
        "max_sensitivity_payout_rate", "max_sensitivity_estimated_payout",
    }
    assert required_keys.issubset(payload.keys())


def test_feature_payload_is_json_serialisable() -> None:
    row = _input_row()
    encoders = build_category_encoders([row])
    payload = build_engineered_feature_payload(row, encoders)
    json.dumps(payload)  # should not raise


def test_feature_payload_baseline_triggered_flag_true_when_rate_positive() -> None:
    row = _input_row(baseline_payout_rate=0.2)
    encoders = build_category_encoders([row])
    payload = build_engineered_feature_payload(row, encoders)
    assert payload["baseline_triggered_flag"] is True


def test_record_contains_canonical_fields() -> None:
    row = _input_row()
    encoders = build_category_encoders([row])
    rec = build_model_training_record(row, encoders)
    assert set(rec.keys()) == {
        "asset_id",
        "as_of_date",
        "feature_version",
        "target_extreme_rainfall_event",
        "engineered_features_json",
    }
    assert rec["feature_version"] == DEFAULT_FEATURE_VERSION
    assert isinstance(rec["target_extreme_rainfall_event"], bool)


def test_record_target_reflects_extreme_flag() -> None:
    row = _input_row(extreme_rainfall_flag=True)
    encoders = build_category_encoders([row])
    rec = build_model_training_record(row, encoders)
    assert rec["target_extreme_rainfall_event"] is True


def _good_record(asset_id: str = "VIC0001") -> dict[str, Any]:
    row = _input_row(asset_id=asset_id)
    encoders = build_category_encoders([row])
    return build_model_training_record(row, encoders)


def test_schema_validates_good_record() -> None:
    rec = ModelTrainingRecord.model_validate(_good_record())
    assert rec.feature_version == DEFAULT_FEATURE_VERSION


def test_schema_rejects_missing_feature_version() -> None:
    bad = _good_record()
    bad["feature_version"] = ""
    with pytest.raises(ValidationError):
        ModelTrainingRecord.model_validate(bad)


def test_validate_accepts_unique_records() -> None:
    out = validate_model_training_records(
        [_good_record("VIC0001"), _good_record("VIC0002")]
    )
    assert len(out) == 2


def test_validate_rejects_duplicate_triplet() -> None:
    with pytest.raises(ValueError, match="Duplicate"):
        validate_model_training_records(
            [_good_record("VIC0001"), _good_record("VIC0001")]
        )


def test_validate_rejects_missing_required_payload_key() -> None:
    rec = _good_record()
    del rec["engineered_features_json"]["rainfall_3d_mm"]
    with pytest.raises(ValueError, match="missing required keys"):
        validate_model_training_records([rec])


def test_persist_inserts_when_replace_existing_true() -> None:
    records = [_good_record("VIC0001"), _good_record("VIC0002")]
    session = FakeSession()
    n = persist_model_training_data(records, session, replace_existing=True)
    assert n == 2
    assert all(isinstance(o, ModelTrainingData) for o in session.added)
    assert session.committed is True


def test_persist_replace_existing_issues_delete_first() -> None:
    records = [_good_record("VIC0001")]
    session = FakeSession()
    persist_model_training_data(records, session, replace_existing=True)
    deletes = [s for s in session.executes if str(s).lower().startswith("delete")]
    assert len(deletes) == 1


def test_persist_skips_existing_when_replace_existing_false() -> None:
    records = [_good_record("VIC0001"), _good_record("VIC0002")]
    session = FakeSession(
        existing_keys={("VIC0001", date(2025, 12, 31), DEFAULT_FEATURE_VERSION)}
    )
    n = persist_model_training_data(records, session, replace_existing=False)
    assert n == 1
    assert {o.asset_id for o in session.added} == {"VIC0002"}


def test_persist_validates_before_insert() -> None:
    bad = _good_record()
    bad["feature_version"] = ""
    session = FakeSession()
    with pytest.raises(ValidationError):
        persist_model_training_data([bad], session)
    assert session.committed is False


def test_persist_rolls_back_on_failure() -> None:
    records = [_good_record("VIC0001")]

    class Boom(FakeSession):
        def add_all(self, objs: list[Any]) -> None:
            raise RuntimeError("boom")

    session = Boom()
    with pytest.raises(RuntimeError):
        persist_model_training_data(records, session)
    assert session.rolled_back is True
    assert session.committed is False


def test_persist_returns_zero_for_empty_input() -> None:
    session = FakeSession()
    assert persist_model_training_data([], session) == 0
    assert session.committed is False
