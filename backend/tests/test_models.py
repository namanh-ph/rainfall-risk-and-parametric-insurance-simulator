"""Schema-level tests for the ORM models.

These checks operate on metadata only - they do not require a live
PostgreSQL database.
"""

from __future__ import annotations

import pytest

from src.db.models import (
    Asset,
    AssetRiskScore,
    AssetStationMapping,
    LgaBoundary,
    ModelPrediction,
    ModelTrainingData,
    PayoutResult,
    RainfallFeature,
    RainfallObservation,
    RainfallStation,
    SimulationRun,
)

CANONICAL_TABLE_NAMES = {
    Asset: "assets",
    RainfallStation: "rainfall_stations",
    RainfallObservation: "rainfall_observations",
    AssetStationMapping: "asset_station_mapping",
    LgaBoundary: "lga_boundaries",
    RainfallFeature: "rainfall_features",
    AssetRiskScore: "asset_risk_scores",
    SimulationRun: "simulation_runs",
    PayoutResult: "payout_results",
    ModelTrainingData: "model_training_data",
    ModelPrediction: "model_predictions",
}


@pytest.mark.parametrize(("model", "tablename"), list(CANONICAL_TABLE_NAMES.items()))
def test_each_model_has_canonical_tablename(model, tablename) -> None:
    assert model.__tablename__ == tablename


def test_asset_has_required_columns() -> None:
    expected = {
        "asset_id",
        "business_type",
        "industry",
        "postcode",
        "lga_code",
        "latitude",
        "longitude",
        "asset_value",
        "annual_revenue",
        "coverage_limit",
        "geom",
        "created_at",
        "updated_at",
    }
    assert expected.issubset(set(Asset.__table__.columns.keys()))


def test_rainfall_station_has_geom_column() -> None:
    assert "geom" in RainfallStation.__table__.columns
    geom = RainfallStation.__table__.columns["geom"]
    # GeoAlchemy2 records geometry_type and srid on the type object
    assert getattr(geom.type, "geometry_type", "").upper() == "POINT"
    assert getattr(geom.type, "srid", None) == 4326


def test_lga_boundary_has_multipolygon_geom_column() -> None:
    geom = LgaBoundary.__table__.columns["geom"]
    assert getattr(geom.type, "geometry_type", "").upper() == "MULTIPOLYGON"
    assert getattr(geom.type, "srid", None) == 4326


def test_rainfall_observation_has_station_fk() -> None:
    fks = list(RainfallObservation.__table__.columns["station_id"].foreign_keys)
    assert any(fk.column.table.name == "rainfall_stations" for fk in fks)


def test_payout_results_has_simulation_and_asset_fks() -> None:
    sim_fks = list(PayoutResult.__table__.columns["simulation_id"].foreign_keys)
    asset_fks = list(PayoutResult.__table__.columns["asset_id"].foreign_keys)
    assert any(fk.column.table.name == "simulation_runs" for fk in sim_fks)
    assert any(fk.column.table.name == "assets" for fk in asset_fks)


def test_model_predictions_unique_constraint_on_canonical_columns() -> None:
    expected_cols = {"asset_id", "as_of_date", "model_name", "model_version"}
    found = False
    for constraint in ModelPrediction.__table__.constraints:
        from sqlalchemy import UniqueConstraint

        if isinstance(constraint, UniqueConstraint):
            cols = {col.name for col in constraint.columns}
            if cols == expected_cols:
                found = True
                assert constraint.name == "uq_model_predictions_asset_date_model"
    assert found, "Expected unique constraint on (asset_id, as_of_date, model_name, model_version)"


def test_relationships_declared_where_required() -> None:
    # Asset -> child collections
    assert Asset.rainfall_features.property.mapper.class_ is RainfallFeature
    assert Asset.risk_scores.property.mapper.class_ is AssetRiskScore
    assert Asset.payout_results.property.mapper.class_ is PayoutResult
    assert Asset.training_rows.property.mapper.class_ is ModelTrainingData
    assert Asset.predictions.property.mapper.class_ is ModelPrediction
    # RainfallStation -> children
    assert RainfallStation.observations.property.mapper.class_ is RainfallObservation
    assert RainfallStation.rainfall_features.property.mapper.class_ is RainfallFeature
    # SimulationRun -> payout_results
    assert SimulationRun.payout_results.property.mapper.class_ is PayoutResult


def test_timestamp_columns_present_on_every_model() -> None:
    for model in CANONICAL_TABLE_NAMES:
        cols = model.__table__.columns
        assert "created_at" in cols, f"{model.__name__} missing created_at"
        assert "updated_at" in cols, f"{model.__name__} missing updated_at"


def test_simulation_runs_threshold_config_is_jsonb() -> None:
    col = SimulationRun.__table__.columns["threshold_config"]
    type_repr = repr(col.type).upper()
    assert "JSON" in type_repr  # JSONB inherits from JSON in dialect
