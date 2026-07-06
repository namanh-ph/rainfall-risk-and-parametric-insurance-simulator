"""Tests for the parameterised PostGIS asset-to-LGA join SQL builder"""

from __future__ import annotations

import pytest

from src.geospatial.lga_join import build_asset_lga_join_query


def _sql(stmt) -> str:
    return str(stmt)


def test_query_references_assets_and_lga_boundaries() -> None:
    stmt, _ = build_asset_lga_join_query()
    sql = _sql(stmt)
    assert "assets" in sql
    assert "lga_boundaries" in sql


def test_query_uses_st_covers_and_st_intersects() -> None:
    stmt, _ = build_asset_lga_join_query()
    sql = _sql(stmt)
    assert "ST_Covers" in sql
    assert "ST_Intersects" in sql


def test_query_includes_method_classification_case() -> None:
    stmt, _ = build_asset_lga_join_query()
    sql_lower = _sql(stmt).lower()
    assert "case when st_covers" in sql_lower
    assert "'covers'" in _sql(stmt)
    assert "'intersects'" in _sql(stmt)


def test_query_uses_row_number_with_priority_distance_lga_code_ordering() -> None:
    stmt, _ = build_asset_lga_join_query()
    sql_lower = _sql(stmt).lower()
    assert "row_number()" in sql_lower
    assert "partition by asset_id" in sql_lower
    # Priority: covers → 1, intersects → 2, nearest_fallback → 3
    assert "'covers' then 1" in sql_lower
    assert "'intersects' then 2" in sql_lower
    assert "'nearest_fallback' then 3" in sql_lower
    # Tie-break on distance, then lga_code
    assert "assignment_distance_km asc" in sql_lower
    assert "lga_code asc" in sql_lower


def test_query_returns_unmatched_via_left_join() -> None:
    stmt, _ = build_asset_lga_join_query()
    sql_lower = _sql(stmt).lower()
    assert "left join ranked" in sql_lower
    assert "coalesce(r.assignment_method, 'unmatched')" in sql_lower


def test_query_includes_fallback_st_distance_and_geography() -> None:
    stmt, _ = build_asset_lga_join_query(allow_nearest_fallback=True)
    sql = _sql(stmt)
    assert "ST_Distance" in sql
    assert sql.lower().count("geography(") >= 4  # both sides for distance + KNN ordering
    assert "/ 1000.0" in sql


def test_query_uses_lateral_for_nearest_fallback() -> None:
    stmt, _ = build_asset_lga_join_query(allow_nearest_fallback=True)
    sql_lower = _sql(stmt).lower()
    assert "cross join lateral" in sql_lower
    assert "limit 1" in sql_lower
    assert "<->" in sql_lower  # PostGIS KNN operator


def test_query_disabling_nearest_fallback_removes_fallback_cte() -> None:
    stmt, _ = build_asset_lga_join_query(allow_nearest_fallback=False)
    sql_lower = _sql(stmt).lower()
    assert "fallback_candidates" not in sql_lower
    assert "cross join lateral" not in sql_lower


def test_query_supports_max_fallback_distance_filter() -> None:
    stmt, params = build_asset_lga_join_query(
        allow_nearest_fallback=True, max_fallback_distance_km=50.0
    )
    sql = _sql(stmt)
    assert ":max_fallback_distance_km" in sql
    assert params["max_fallback_distance_km"] == 50.0


def test_query_omits_max_fallback_distance_when_none() -> None:
    stmt, params = build_asset_lga_join_query(
        allow_nearest_fallback=True, max_fallback_distance_km=None
    )
    assert "max_fallback_distance_km" not in params
    assert ":max_fallback_distance_km" not in _sql(stmt)


def test_query_rejects_non_positive_max_fallback_distance() -> None:
    with pytest.raises(ValueError, match="max_fallback_distance_km"):
        build_asset_lga_join_query(max_fallback_distance_km=0)
    with pytest.raises(ValueError, match="max_fallback_distance_km"):
        build_asset_lga_join_query(max_fallback_distance_km=-1.0)


def test_query_supports_asset_ids_filter_via_bind_params() -> None:
    stmt, params = build_asset_lga_join_query(asset_ids=["VIC0001", "VIC0002"])
    sql = _sql(stmt)
    assert "a.asset_id IN" in sql
    assert ":asset_ids" in sql or "POSTCOMPILE_asset_ids" in sql
    assert params["asset_ids"] == ["VIC0001", "VIC0002"]


def test_query_does_not_interpolate_asset_ids_into_sql_text() -> None:
    stmt, _ = build_asset_lga_join_query(
        asset_ids=["VIC0001", "VIC0002", "VIC9999"]
    )
    sql = _sql(stmt)
    for raw_id in ("VIC0001", "VIC0002", "VIC9999"):
        assert raw_id not in sql, f"Raw ID {raw_id!r} leaked into SQL text"


def test_query_omits_asset_filter_when_no_ids() -> None:
    stmt, params = build_asset_lga_join_query(asset_ids=None)
    assert "asset_ids" not in params
    assert ":asset_ids" not in _sql(stmt)


def test_query_supports_combined_asset_ids_and_max_distance() -> None:
    stmt, params = build_asset_lga_join_query(
        asset_ids=["VIC0001"],
        allow_nearest_fallback=True,
        max_fallback_distance_km=10.0,
    )
    sql = _sql(stmt)
    assert ":asset_ids" in sql or "POSTCOMPILE_asset_ids" in sql
    assert ":max_fallback_distance_km" in sql
    assert params["asset_ids"] == ["VIC0001"]
    assert params["max_fallback_distance_km"] == 10.0
