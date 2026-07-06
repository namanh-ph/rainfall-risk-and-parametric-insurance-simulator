"""Tests for the parameterised payout-input SQL builder"""

from __future__ import annotations

from datetime import date

from src.insurance.payout import DEFAULT_AS_OF_DATE, build_payout_input_query


def _sql(stmt) -> str:
    return str(stmt)


def test_query_references_assets_and_rainfall_features() -> None:
    stmt, _ = build_payout_input_query()
    sql_lower = _sql(stmt).lower()
    assert "from assets a" in sql_lower
    assert "rainfall_features" in sql_lower


def test_query_returns_required_columns() -> None:
    stmt, _ = build_payout_input_query()
    sql = _sql(stmt)
    for col in ("asset_id", "coverage_limit", "as_of_date", "rainfall_3d_mm"):
        assert col in sql


def test_query_includes_risk_band_join_when_requested() -> None:
    stmt, _ = build_payout_input_query(include_risk_band=True)
    sql_lower = _sql(stmt).lower()
    assert "asset_risk_scores" in sql_lower
    assert "left join asset_risk_scores" in sql_lower
    assert "ars.risk_band" in _sql(stmt)


def test_query_omits_risk_band_join_when_disabled() -> None:
    stmt, _ = build_payout_input_query(include_risk_band=False)
    sql_lower = _sql(stmt).lower()
    assert "asset_risk_scores" not in sql_lower
    assert "ars." not in sql_lower


def test_query_filters_features_by_as_of_date_via_bound_param() -> None:
    stmt, params = build_payout_input_query()
    sql = _sql(stmt)
    assert "rf.as_of_date = :as_of_date" in sql
    assert params["as_of_date"] == DEFAULT_AS_OF_DATE


def test_query_uses_provided_as_of_date() -> None:
    _stmt, params = build_payout_input_query(as_of_date=date(2024, 6, 30))
    assert params["as_of_date"] == date(2024, 6, 30)


def test_query_supports_asset_ids_filter_via_bind_params() -> None:
    stmt, params = build_payout_input_query(asset_ids=["VIC0001", "VIC0002"])
    sql = _sql(stmt)
    assert "a.asset_id IN" in sql
    assert ":asset_ids" in sql or "POSTCOMPILE_asset_ids" in sql
    assert params["asset_ids"] == ["VIC0001", "VIC0002"]


def test_query_does_not_interpolate_asset_ids_into_sql_text() -> None:
    stmt, _ = build_payout_input_query(asset_ids=["VIC0001", "VIC0002", "VIC9999"])
    sql = _sql(stmt)
    for raw in ("VIC0001", "VIC0002", "VIC9999"):
        assert raw not in sql, f"Raw ID {raw!r} leaked into SQL text"


def test_query_omits_asset_filter_when_no_ids() -> None:
    stmt, params = build_payout_input_query(asset_ids=None)
    assert "asset_ids" not in params
    assert ":asset_ids" not in _sql(stmt)


def test_query_does_not_inline_default_as_of_date_string() -> None:
    stmt, _ = build_payout_input_query()
    assert DEFAULT_AS_OF_DATE.isoformat() not in _sql(stmt)
