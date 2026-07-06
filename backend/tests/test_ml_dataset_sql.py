"""Tests for the parameterised ML training-dataset SQL builder"""

from __future__ import annotations

from datetime import date

from src.ml.dataset import (
    DEFAULT_AS_OF_DATE,
    build_model_training_data_query,
)


def _sql(stmt) -> str:
    return str(stmt)


def test_query_references_all_required_tables() -> None:
    stmt, _ = build_model_training_data_query()
    sql_lower = _sql(stmt).lower()
    assert "from assets a" in sql_lower
    assert "asset_station_mapping" in sql_lower
    assert "rainfall_features" in sql_lower
    assert "asset_risk_scores" in sql_lower


def test_query_left_joins_lga_boundaries() -> None:
    sql_lower = _sql(build_model_training_data_query()[0]).lower()
    assert "left join lga_boundaries" in sql_lower


def test_query_left_joins_baseline_payout_results() -> None:
    sql_lower = _sql(build_model_training_data_query()[0]).lower()
    assert "left join payout_results pr_base" in sql_lower
    assert "pr_base.simulation_id = :baseline_simulation_id" in sql_lower


def test_query_left_joins_sensitive_payout_results() -> None:
    sql_lower = _sql(build_model_training_data_query()[0]).lower()
    assert "left join payout_results pr_t040" in sql_lower
    assert "left join payout_results pr_t020" in sql_lower
    assert "pr_t040.simulation_id = :sensitive_simulation_id" in sql_lower
    assert "pr_t020.simulation_id = :very_sensitive_simulation_id" in sql_lower


def test_query_filters_features_by_as_of_date_via_bound_param() -> None:
    stmt, params = build_model_training_data_query()
    sql = _sql(stmt)
    assert "rf.as_of_date = :as_of_date" in sql
    assert "ars.as_of_date = :as_of_date" in sql
    assert params["as_of_date"] == DEFAULT_AS_OF_DATE


def test_query_uses_provided_as_of_date() -> None:
    _stmt, params = build_model_training_data_query(as_of_date=date(2024, 6, 30))
    assert params["as_of_date"] == date(2024, 6, 30)


def test_query_supports_asset_ids_filter_via_bind_params() -> None:
    stmt, params = build_model_training_data_query(asset_ids=["VIC0001", "VIC0002"])
    sql = _sql(stmt)
    assert "a.asset_id IN" in sql
    assert ":asset_ids" in sql or "POSTCOMPILE_asset_ids" in sql
    assert params["asset_ids"] == ["VIC0001", "VIC0002"]


def test_query_does_not_interpolate_asset_ids_into_sql_text() -> None:
    stmt, _ = build_model_training_data_query(
        asset_ids=["VIC0001", "VIC0002", "VIC9999"]
    )
    sql = _sql(stmt)
    for raw in ("VIC0001", "VIC0002", "VIC9999"):
        assert raw not in sql, f"Raw ID {raw!r} leaked into SQL text"


def test_query_uses_bound_params_for_simulation_ids() -> None:
    stmt, params = build_model_training_data_query()
    sql = _sql(stmt)
    assert ":baseline_simulation_id" in sql
    assert ":sensitive_simulation_id" in sql
    assert ":very_sensitive_simulation_id" in sql
    # Default baseline and the derived sweep IDs land in params
    assert params["baseline_simulation_id"] == "DEFAULT_2025_BASELINE"
    assert params["sensitive_simulation_id"] == "SWEEP_2025_T040"
    assert params["very_sensitive_simulation_id"] == "SWEEP_2025_T020"


def test_query_omits_asset_filter_when_no_ids() -> None:
    stmt, params = build_model_training_data_query(asset_ids=None)
    assert "asset_ids" not in params
    assert ":asset_ids" not in _sql(stmt)


def test_query_does_not_reference_model_predictions() -> None:
    sql_lower = _sql(build_model_training_data_query()[0]).lower()
    assert "model_predictions" not in sql_lower
