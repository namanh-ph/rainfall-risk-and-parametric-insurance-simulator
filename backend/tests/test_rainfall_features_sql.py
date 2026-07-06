"""Tests for the parameterised rainfall-feature data-access SQL builder"""

from __future__ import annotations

from datetime import date, timedelta

from src.features.rainfall_features import (
    DEFAULT_AS_OF_DATE,
    LOOKBACK_DAYS,
    build_asset_rainfall_feature_query,
)


def _sql(stmt) -> str:
    return str(stmt)


def test_query_references_all_required_tables() -> None:
    stmt, _ = build_asset_rainfall_feature_query()
    sql_lower = _sql(stmt).lower()
    assert "from assets a" in sql_lower
    assert "asset_station_mapping" in sql_lower
    assert "rainfall_stations" in sql_lower
    assert "rainfall_observations" in sql_lower


def test_query_returns_required_columns() -> None:
    stmt, _ = build_asset_rainfall_feature_query()
    sql = _sql(stmt)
    assert "asset_id" in sql
    assert "station_id" in sql
    assert "observation_date" in sql
    assert "rainfall_mm" in sql


def test_query_uses_left_join_on_observations() -> None:
    stmt, _ = build_asset_rainfall_feature_query()
    sql_lower = _sql(stmt).lower()
    assert "left join rainfall_observations" in sql_lower


def test_query_filters_observation_date_using_bound_params() -> None:
    stmt, params = build_asset_rainfall_feature_query()
    sql = _sql(stmt)
    assert ":lookback_start" in sql
    assert ":as_of_date" in sql
    assert "observation_date BETWEEN :lookback_start AND :as_of_date" in sql
    assert params["as_of_date"] == DEFAULT_AS_OF_DATE
    assert params["lookback_start"] == DEFAULT_AS_OF_DATE - timedelta(days=LOOKBACK_DAYS - 1)


def test_query_uses_provided_as_of_date() -> None:
    _stmt, params = build_asset_rainfall_feature_query(as_of_date=date(2024, 6, 30))
    assert params["as_of_date"] == date(2024, 6, 30)
    assert params["lookback_start"] == date(2024, 6, 30) - timedelta(days=364)


def test_query_supports_asset_ids_filter_via_bind_params() -> None:
    stmt, params = build_asset_rainfall_feature_query(asset_ids=["VIC0001", "VIC0002"])
    sql = _sql(stmt)
    assert "a.asset_id IN" in sql
    assert ":asset_ids" in sql or "POSTCOMPILE_asset_ids" in sql
    assert params["asset_ids"] == ["VIC0001", "VIC0002"]


def test_query_does_not_interpolate_asset_ids_into_sql_text() -> None:
    stmt, _ = build_asset_rainfall_feature_query(
        asset_ids=["VIC0001", "VIC0002", "VIC9999"]
    )
    sql = _sql(stmt)
    for raw_id in ("VIC0001", "VIC0002", "VIC9999"):
        assert raw_id not in sql, f"Raw ID {raw_id!r} leaked into SQL"


def test_query_omits_asset_filter_when_no_ids() -> None:
    stmt, params = build_asset_rainfall_feature_query(asset_ids=None)
    assert "asset_ids" not in params
    assert ":asset_ids" not in _sql(stmt)


def test_query_uses_bound_parameter_for_as_of_date() -> None:
    stmt, params = build_asset_rainfall_feature_query()
    sql = _sql(stmt)
    # The SQL should not contain a literal date string for as_of_date
    assert DEFAULT_AS_OF_DATE.isoformat() not in sql
    assert params["as_of_date"] == DEFAULT_AS_OF_DATE
