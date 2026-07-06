"""Verify that Base.metadata holds the schema"""

from __future__ import annotations

import src.db  # noqa: F401 - register all models
from src.db.base import Base

CANONICAL_TABLES = {
    "assets",
    "rainfall_stations",
    "rainfall_observations",
    "asset_station_mapping",
    "lga_boundaries",
    "rainfall_features",
    "asset_risk_scores",
    "simulation_runs",
    "payout_results",
    "model_training_data",
    "model_predictions",
}


def test_metadata_contains_all_canonical_tables() -> None:
    table_names = set(Base.metadata.tables.keys())
    missing = CANONICAL_TABLES - table_names
    assert not missing, f"Missing tables in metadata: {missing}"


def test_assets_has_geom_column() -> None:
    assert "geom" in Base.metadata.tables["assets"].columns


def test_rainfall_stations_has_geom_column() -> None:
    assert "geom" in Base.metadata.tables["rainfall_stations"].columns


def test_lga_boundaries_has_geom_column() -> None:
    assert "geom" in Base.metadata.tables["lga_boundaries"].columns


def test_rainfall_observations_station_fk_targets_rainfall_stations() -> None:
    table = Base.metadata.tables["rainfall_observations"]
    fks = list(table.columns["station_id"].foreign_keys)
    assert fks, "expected a foreign key on rainfall_observations.station_id"
    assert any(fk.column.table.name == "rainfall_stations" for fk in fks)


def test_payout_results_has_simulation_and_asset_fks() -> None:
    table = Base.metadata.tables["payout_results"]
    sim_fks = list(table.columns["simulation_id"].foreign_keys)
    asset_fks = list(table.columns["asset_id"].foreign_keys)
    assert any(fk.column.table.name == "simulation_runs" for fk in sim_fks)
    assert any(fk.column.table.name == "assets" for fk in asset_fks)


def test_model_predictions_has_expected_unique_constraint() -> None:
    from sqlalchemy import UniqueConstraint

    table = Base.metadata.tables["model_predictions"]
    expected_cols = {"asset_id", "as_of_date", "model_name", "model_version"}
    matches = [
        constraint
        for constraint in table.constraints
        if isinstance(constraint, UniqueConstraint)
        and {c.name for c in constraint.columns} == expected_cols
    ]
    assert matches, "Expected unique(asset_id, as_of_date, model_name, model_version)"


def test_spatial_geom_columns_use_srid_4326() -> None:
    for table_name in ("assets", "rainfall_stations", "lga_boundaries"):
        geom = Base.metadata.tables[table_name].columns["geom"]
        assert getattr(geom.type, "srid", None) == 4326, table_name
