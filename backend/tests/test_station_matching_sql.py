"""Tests for the parameterised PostGIS nearest-station SQL builder"""

from __future__ import annotations

import pytest

from src.geospatial.station_matching import build_nearest_station_query


def _sql(stmt) -> str:
    return str(stmt)


def test_query_references_assets_and_rainfall_stations() -> None:
    stmt, _ = build_nearest_station_query()
    sql = _sql(stmt)
    assert "assets" in sql
    assert "rainfall_stations" in sql


def test_query_uses_st_distance_and_geography() -> None:
    stmt, _ = build_nearest_station_query()
    sql = _sql(stmt)
    assert "ST_Distance" in sql
    # geography(...) cast must appear for both sides
    assert sql.lower().count("geography(") >= 2


def test_query_divides_distance_by_1000() -> None:
    stmt, _ = build_nearest_station_query()
    sql = _sql(stmt)
    assert "/ 1000.0" in sql


def test_query_uses_lateral_join() -> None:
    stmt, _ = build_nearest_station_query()
    sql = _sql(stmt).lower()
    assert "lateral" in sql
    assert "limit 1" in sql


def test_query_orders_by_knn_operator() -> None:
    stmt, _ = build_nearest_station_query()
    sql = _sql(stmt).lower()
    assert "<->" in sql  # PostGIS KNN operator


def test_query_supports_asset_ids_filter_via_bind_params() -> None:
    stmt, params = build_nearest_station_query(asset_ids=["VIC0001", "VIC0002"])
    sql = _sql(stmt)
    assert "asset.asset_id IN" in sql
    # Expanding bindparam may render as ":asset_ids" or as
    # "__[POSTCOMPILE_asset_ids]" depending on SQLAlchemy compile-state
    assert ":asset_ids" in sql or "POSTCOMPILE_asset_ids" in sql
    assert params["asset_ids"] == ["VIC0001", "VIC0002"]


def test_query_does_not_interpolate_asset_ids_into_sql_text() -> None:
    stmt, _ = build_nearest_station_query(
        asset_ids=["VIC0001", "VIC0002", "VIC9999"]
    )
    sql = _sql(stmt)
    for raw_id in ("VIC0001", "VIC0002", "VIC9999"):
        assert raw_id not in sql, f"Raw ID {raw_id!r} leaked into SQL text"


def test_query_omits_filter_when_asset_ids_none() -> None:
    stmt, params = build_nearest_station_query(asset_ids=None)
    assert "asset_ids" not in params
    assert ":asset_ids" not in _sql(stmt)


def test_query_supports_max_distance_filter() -> None:
    stmt, params = build_nearest_station_query(max_distance_km=75.0)
    sql = _sql(stmt)
    assert ":max_distance_km" in sql
    assert "station_distance_km <= :max_distance_km" in sql
    assert params["max_distance_km"] == 75.0


def test_query_omits_max_distance_when_none() -> None:
    stmt, params = build_nearest_station_query(max_distance_km=None)
    assert "max_distance_km" not in params
    assert ":max_distance_km" not in _sql(stmt)


def test_query_rejects_non_positive_max_distance() -> None:
    with pytest.raises(ValueError, match="max_distance_km"):
        build_nearest_station_query(max_distance_km=0)
    with pytest.raises(ValueError, match="max_distance_km"):
        build_nearest_station_query(max_distance_km=-1.0)


def test_query_supports_combined_filters() -> None:
    stmt, params = build_nearest_station_query(
        asset_ids=["VIC0001"], max_distance_km=50.0
    )
    sql = _sql(stmt)
    assert ":asset_ids" in sql or "POSTCOMPILE_asset_ids" in sql
    assert ":max_distance_km" in sql
    assert params["asset_ids"] == ["VIC0001"]
    assert params["max_distance_km"] == 50.0
