"""create core PostGIS schema

Revision ID: 20260506_0001
Revises:
Create Date: 2026-05-06

This migration is the schema bootstrap for the simulator.
It enables PostGIS, then creates the eleven core tables defined in
PostGIS schema, plus all foreign keys, unique
constraints, check constraints, B-tree indexes, and GIST spatial indexes.
"""

from __future__ import annotations

from typing import Sequence

import sqlalchemy as sa
from alembic import op
from geoalchemy2 import Geometry
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic
revision: str = "20260506_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


RISK_BAND_VALUES = "'Low', 'Medium', 'High', 'Severe'"
TRIGGER_STATUS_VALUES = "'triggered', 'not_triggered'"


def _create_geom_index(table: str) -> None:
    op.create_index(
        f"ix_{table}_geom",
        table,
        ["geom"],
        postgresql_using="gist",
    )


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")

    op.create_table(
        "lga_boundaries",
        sa.Column("lga_code", sa.String(length=16), nullable=False),
        sa.Column("lga_name", sa.String(length=128), nullable=False),
        sa.Column(
            "state",
            sa.String(length=8),
            nullable=False,
            server_default=sa.text("'VIC'"),
        ),
        sa.Column(
            "geom",
            Geometry(geometry_type="MULTIPOLYGON", srid=4326, spatial_index=False),
            nullable=False,
        ),
        sa.Column(
            "data_source",
            sa.String(length=64),
            nullable=False,
            server_default=sa.text("'abs'"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("lga_code", name="pk_lga_boundaries"),
        sa.UniqueConstraint("lga_name", "state", name="uq_lga_boundaries_name_state"),
    )
    _create_geom_index("lga_boundaries")
    op.create_index("ix_lga_boundaries_lga_name", "lga_boundaries", ["lga_name"])
    op.create_index("ix_lga_boundaries_state", "lga_boundaries", ["state"])

    op.create_table(
        "rainfall_stations",
        sa.Column("station_id", sa.String(length=32), nullable=False),
        sa.Column("station_name", sa.String(length=255), nullable=False),
        sa.Column("latitude", sa.Numeric(9, 6), nullable=False),
        sa.Column("longitude", sa.Numeric(9, 6), nullable=False),
        sa.Column("elevation_m", sa.Numeric(7, 2), nullable=True),
        sa.Column(
            "geom",
            Geometry(geometry_type="POINT", srid=4326, spatial_index=False),
            nullable=False,
        ),
        sa.Column(
            "data_source",
            sa.String(length=64),
            nullable=False,
            server_default=sa.text("'synthetic'"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("station_id", name="pk_rainfall_stations"),
        sa.CheckConstraint(
            "latitude BETWEEN -90 AND 90", name="ck_rainfall_stations_latitude_range"
        ),
        sa.CheckConstraint(
            "longitude BETWEEN -180 AND 180",
            name="ck_rainfall_stations_longitude_range",
        ),
    )
    _create_geom_index("rainfall_stations")
    op.create_index(
        "ix_rainfall_stations_station_name", "rainfall_stations", ["station_name"]
    )
    op.create_index(
        "ix_rainfall_stations_data_source", "rainfall_stations", ["data_source"]
    )

    op.create_table(
        "assets",
        sa.Column("asset_id", sa.String(length=64), nullable=False),
        sa.Column("business_type", sa.String(length=64), nullable=False),
        sa.Column("industry", sa.String(length=128), nullable=False),
        sa.Column("postcode", sa.String(length=128), nullable=False),
        sa.Column("lga_code", sa.String(length=16), nullable=True),
        sa.Column("latitude", sa.Numeric(9, 6), nullable=False),
        sa.Column("longitude", sa.Numeric(9, 6), nullable=False),
        sa.Column("asset_value", sa.Numeric(14, 2), nullable=False),
        sa.Column("annual_revenue", sa.Numeric(14, 2), nullable=True),
        sa.Column("coverage_limit", sa.Numeric(14, 2), nullable=False),
        sa.Column(
            "geom",
            Geometry(geometry_type="POINT", srid=4326, spatial_index=False),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("asset_id", name="pk_assets"),
        sa.ForeignKeyConstraint(
            ["lga_code"],
            ["lga_boundaries.lga_code"],
            name="fk_assets_lga_code_lga_boundaries",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint("asset_value >= 0", name="ck_assets_asset_value_non_negative"),
        sa.CheckConstraint(
            "annual_revenue IS NULL OR annual_revenue >= 0",
            name="ck_assets_annual_revenue_non_negative",
        ),
        sa.CheckConstraint(
            "coverage_limit >= 0", name="ck_assets_coverage_limit_non_negative"
        ),
        sa.CheckConstraint("latitude BETWEEN -90 AND 90", name="ck_assets_latitude_range"),
        sa.CheckConstraint(
            "longitude BETWEEN -180 AND 180", name="ck_assets_longitude_range"
        ),
    )
    _create_geom_index("assets")
    op.create_index("ix_assets_postcode", "assets", ["postcode"])
    op.create_index("ix_assets_industry", "assets", ["industry"])
    op.create_index("ix_assets_lga_code", "assets", ["lga_code"])

    op.create_table(
        "rainfall_observations",
        sa.Column(
            "observation_id",
            sa.Integer(),
            sa.Identity(always=False),
            nullable=False,
        ),
        sa.Column("station_id", sa.String(length=32), nullable=False),
        sa.Column("observation_date", sa.Date(), nullable=False),
        sa.Column("rainfall_mm", sa.Numeric(7, 2), nullable=False),
        sa.Column("quality_flag", sa.String(length=8), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("observation_id", name="pk_rainfall_observations"),
        sa.ForeignKeyConstraint(
            ["station_id"],
            ["rainfall_stations.station_id"],
            name="fk_rainfall_observations_station_id_rainfall_stations",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "rainfall_mm >= 0",
            name="ck_rainfall_observations_rainfall_mm_non_negative",
        ),
        sa.UniqueConstraint(
            "station_id",
            "observation_date",
            name="uq_rainfall_observations_station_date",
        ),
    )
    op.create_index(
        "ix_rainfall_observations_station_id", "rainfall_observations", ["station_id"]
    )
    op.create_index(
        "ix_rainfall_observations_observation_date",
        "rainfall_observations",
        ["observation_date"],
    )
    op.create_index(
        "ix_rainfall_observations_station_date_combo",
        "rainfall_observations",
        ["station_id", "observation_date"],
    )

    op.create_table(
        "asset_station_mapping",
        sa.Column("asset_id", sa.String(length=64), nullable=False),
        sa.Column("station_id", sa.String(length=32), nullable=False),
        sa.Column("station_distance_km", sa.Numeric(8, 3), nullable=False),
        sa.Column("station_confidence_weight", sa.Numeric(4, 3), nullable=False),
        sa.Column(
            "matched_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("asset_id", name="pk_asset_station_mapping"),
        sa.ForeignKeyConstraint(
            ["asset_id"],
            ["assets.asset_id"],
            name="fk_asset_station_mapping_asset_id_assets",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["station_id"],
            ["rainfall_stations.station_id"],
            name="fk_asset_station_mapping_station_id_rainfall_stations",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "station_distance_km >= 0",
            name="ck_asset_station_mapping_distance_non_negative",
        ),
        sa.CheckConstraint(
            "station_confidence_weight BETWEEN 0.50 AND 1.00",
            name="ck_asset_station_mapping_confidence_range",
        ),
    )
    op.create_index(
        "ix_asset_station_mapping_station_id", "asset_station_mapping", ["station_id"]
    )
    op.create_index(
        "ix_asset_station_mapping_distance",
        "asset_station_mapping",
        ["station_distance_km"],
    )

    op.create_table(
        "rainfall_features",
        sa.Column(
            "feature_id",
            sa.Integer(),
            sa.Identity(always=False),
            nullable=False,
        ),
        sa.Column("asset_id", sa.String(length=64), nullable=False),
        sa.Column("station_id", sa.String(length=32), nullable=False),
        sa.Column("as_of_date", sa.Date(), nullable=False),
        sa.Column("rainfall_1d_mm", sa.Numeric(7, 2), nullable=False),
        sa.Column("rainfall_3d_mm", sa.Numeric(7, 2), nullable=False),
        sa.Column("rainfall_7d_mm", sa.Numeric(7, 2), nullable=False),
        sa.Column("rainfall_30d_mm", sa.Numeric(7, 2), nullable=False),
        sa.Column("rainfall_p95_station", sa.Numeric(7, 2), nullable=True),
        sa.Column("rainfall_p99_station", sa.Numeric(7, 2), nullable=True),
        sa.Column("rainfall_percentile", sa.Numeric(6, 4), nullable=True),
        sa.Column("max_365d_rainfall_mm", sa.Numeric(7, 2), nullable=True),
        sa.Column("days_above_p95_365d", sa.Integer(), nullable=True),
        sa.Column(
            "extreme_rainfall_flag",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("feature_id", name="pk_rainfall_features"),
        sa.ForeignKeyConstraint(
            ["asset_id"],
            ["assets.asset_id"],
            name="fk_rainfall_features_asset_id_assets",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["station_id"],
            ["rainfall_stations.station_id"],
            name="fk_rainfall_features_station_id_rainfall_stations",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "rainfall_1d_mm >= 0", name="ck_rainfall_features_rainfall_1d_non_negative"
        ),
        sa.CheckConstraint(
            "rainfall_3d_mm >= 0", name="ck_rainfall_features_rainfall_3d_non_negative"
        ),
        sa.CheckConstraint(
            "rainfall_7d_mm >= 0", name="ck_rainfall_features_rainfall_7d_non_negative"
        ),
        sa.CheckConstraint(
            "rainfall_30d_mm >= 0",
            name="ck_rainfall_features_rainfall_30d_non_negative",
        ),
        sa.CheckConstraint(
            "rainfall_p95_station IS NULL OR rainfall_p95_station >= 0",
            name="ck_rainfall_features_p95_non_negative",
        ),
        sa.CheckConstraint(
            "rainfall_p99_station IS NULL OR rainfall_p99_station >= 0",
            name="ck_rainfall_features_p99_non_negative",
        ),
        sa.CheckConstraint(
            "max_365d_rainfall_mm IS NULL OR max_365d_rainfall_mm >= 0",
            name="ck_rainfall_features_max_365d_non_negative",
        ),
        sa.CheckConstraint(
            "rainfall_percentile IS NULL OR rainfall_percentile BETWEEN 0 AND 1",
            name="ck_rainfall_features_percentile_range",
        ),
        sa.CheckConstraint(
            "days_above_p95_365d IS NULL OR days_above_p95_365d >= 0",
            name="ck_rainfall_features_days_above_p95_non_negative",
        ),
        sa.UniqueConstraint(
            "asset_id", "as_of_date", name="uq_rainfall_features_asset_date"
        ),
    )
    op.create_index("ix_rainfall_features_asset_id", "rainfall_features", ["asset_id"])
    op.create_index(
        "ix_rainfall_features_station_id", "rainfall_features", ["station_id"]
    )
    op.create_index(
        "ix_rainfall_features_as_of_date", "rainfall_features", ["as_of_date"]
    )
    op.create_index(
        "ix_rainfall_features_extreme_flag",
        "rainfall_features",
        ["extreme_rainfall_flag"],
    )

    op.create_table(
        "asset_risk_scores",
        sa.Column(
            "risk_score_id",
            sa.Integer(),
            sa.Identity(always=False),
            nullable=False,
        ),
        sa.Column("asset_id", sa.String(length=64), nullable=False),
        sa.Column("as_of_date", sa.Date(), nullable=False),
        sa.Column("rainfall_extreme_score", sa.Numeric(6, 2), nullable=False),
        sa.Column("exposure_weight", sa.Numeric(5, 3), nullable=False),
        sa.Column("vulnerability_weight", sa.Numeric(5, 3), nullable=False),
        sa.Column("station_confidence_weight", sa.Numeric(4, 3), nullable=False),
        sa.Column("raw_score", sa.Numeric(8, 3), nullable=False),
        sa.Column("risk_score", sa.Numeric(6, 2), nullable=False),
        sa.Column("risk_band", sa.String(length=16), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("risk_score_id", name="pk_asset_risk_scores"),
        sa.ForeignKeyConstraint(
            ["asset_id"],
            ["assets.asset_id"],
            name="fk_asset_risk_scores_asset_id_assets",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "rainfall_extreme_score BETWEEN 0 AND 100",
            name="ck_asset_risk_scores_extreme_range",
        ),
        sa.CheckConstraint(
            "exposure_weight > 0", name="ck_asset_risk_scores_exposure_positive"
        ),
        sa.CheckConstraint(
            "vulnerability_weight > 0",
            name="ck_asset_risk_scores_vulnerability_positive",
        ),
        sa.CheckConstraint(
            "station_confidence_weight BETWEEN 0.50 AND 1.00",
            name="ck_asset_risk_scores_confidence_range",
        ),
        sa.CheckConstraint(
            "risk_score BETWEEN 0 AND 100", name="ck_asset_risk_scores_score_range"
        ),
        sa.CheckConstraint(
            f"risk_band IN ({RISK_BAND_VALUES})", name="ck_asset_risk_scores_band"
        ),
        sa.UniqueConstraint(
            "asset_id", "as_of_date", name="uq_asset_risk_scores_asset_date"
        ),
    )
    op.create_index("ix_asset_risk_scores_asset_id", "asset_risk_scores", ["asset_id"])
    op.create_index(
        "ix_asset_risk_scores_as_of_date", "asset_risk_scores", ["as_of_date"]
    )
    op.create_index(
        "ix_asset_risk_scores_risk_band", "asset_risk_scores", ["risk_band"]
    )
    op.create_index(
        "ix_asset_risk_scores_risk_score", "asset_risk_scores", ["risk_score"]
    )

    op.create_table(
        "simulation_runs",
        sa.Column("simulation_id", sa.String(length=64), nullable=False),
        sa.Column("simulation_name", sa.String(length=128), nullable=False),
        sa.Column("as_of_date", sa.Date(), nullable=False),
        sa.Column("threshold_config", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "coverage_multiplier",
            sa.Numeric(5, 3),
            nullable=False,
            server_default=sa.text("1.0"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("simulation_id", name="pk_simulation_runs"),
        sa.CheckConstraint(
            "coverage_multiplier > 0",
            name="ck_simulation_runs_coverage_multiplier_positive",
        ),
    )
    op.create_index("ix_simulation_runs_as_of_date", "simulation_runs", ["as_of_date"])
    op.create_index(
        "ix_simulation_runs_simulation_name", "simulation_runs", ["simulation_name"]
    )

    op.create_table(
        "payout_results",
        sa.Column(
            "payout_result_id",
            sa.Integer(),
            sa.Identity(always=False),
            nullable=False,
        ),
        sa.Column("simulation_id", sa.String(length=64), nullable=False),
        sa.Column("asset_id", sa.String(length=64), nullable=False),
        sa.Column("rainfall_3d_mm", sa.Numeric(7, 2), nullable=False),
        sa.Column("trigger_status", sa.String(length=32), nullable=False),
        sa.Column("payout_rate", sa.Numeric(4, 3), nullable=False),
        sa.Column("coverage_limit", sa.Numeric(14, 2), nullable=False),
        sa.Column("estimated_payout", sa.Numeric(14, 2), nullable=False),
        sa.Column("risk_band", sa.String(length=16), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("payout_result_id", name="pk_payout_results"),
        sa.ForeignKeyConstraint(
            ["simulation_id"],
            ["simulation_runs.simulation_id"],
            name="fk_payout_results_simulation_id_simulation_runs",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["asset_id"],
            ["assets.asset_id"],
            name="fk_payout_results_asset_id_assets",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "rainfall_3d_mm >= 0",
            name="ck_payout_results_rainfall_3d_non_negative",
        ),
        sa.CheckConstraint(
            f"trigger_status IN ({TRIGGER_STATUS_VALUES})",
            name="ck_payout_results_trigger_status",
        ),
        sa.CheckConstraint(
            "payout_rate BETWEEN 0 AND 1",
            name="ck_payout_results_payout_rate_range",
        ),
        sa.CheckConstraint(
            "coverage_limit >= 0",
            name="ck_payout_results_coverage_limit_non_negative",
        ),
        sa.CheckConstraint(
            "estimated_payout >= 0",
            name="ck_payout_results_estimated_payout_non_negative",
        ),
        sa.CheckConstraint(
            f"risk_band IS NULL OR risk_band IN ({RISK_BAND_VALUES})",
            name="ck_payout_results_risk_band",
        ),
        sa.UniqueConstraint(
            "simulation_id", "asset_id", name="uq_payout_results_simulation_asset"
        ),
    )
    op.create_index(
        "ix_payout_results_simulation_id", "payout_results", ["simulation_id"]
    )
    op.create_index("ix_payout_results_asset_id", "payout_results", ["asset_id"])
    op.create_index(
        "ix_payout_results_trigger_status", "payout_results", ["trigger_status"]
    )
    op.create_index(
        "ix_payout_results_estimated_payout", "payout_results", ["estimated_payout"]
    )

    op.create_table(
        "model_training_data",
        sa.Column(
            "training_row_id",
            sa.Integer(),
            sa.Identity(always=False),
            nullable=False,
        ),
        sa.Column("asset_id", sa.String(length=64), nullable=False),
        sa.Column("as_of_date", sa.Date(), nullable=False),
        sa.Column("feature_version", sa.String(length=32), nullable=False),
        sa.Column("target_extreme_rainfall_event", sa.Boolean(), nullable=False),
        sa.Column(
            "engineered_features_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("training_row_id", name="pk_model_training_data"),
        sa.ForeignKeyConstraint(
            ["asset_id"],
            ["assets.asset_id"],
            name="fk_model_training_data_asset_id_assets",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "asset_id",
            "as_of_date",
            "feature_version",
            name="uq_model_training_data_asset_date_version",
        ),
    )
    op.create_index(
        "ix_model_training_data_asset_id", "model_training_data", ["asset_id"]
    )
    op.create_index(
        "ix_model_training_data_as_of_date", "model_training_data", ["as_of_date"]
    )
    op.create_index(
        "ix_model_training_data_feature_version",
        "model_training_data",
        ["feature_version"],
    )
    op.create_index(
        "ix_model_training_data_target_extreme_event",
        "model_training_data",
        ["target_extreme_rainfall_event"],
    )

    op.create_table(
        "model_predictions",
        sa.Column(
            "prediction_id",
            sa.Integer(),
            sa.Identity(always=False),
            nullable=False,
        ),
        sa.Column("asset_id", sa.String(length=64), nullable=False),
        sa.Column("as_of_date", sa.Date(), nullable=False),
        sa.Column("model_name", sa.String(length=128), nullable=False),
        sa.Column("model_version", sa.String(length=64), nullable=False),
        sa.Column("ml_risk_probability", sa.Numeric(6, 5), nullable=False),
        sa.Column("ml_risk_rank", sa.Integer(), nullable=True),
        sa.Column("top_risk_driver", sa.String(length=128), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("prediction_id", name="pk_model_predictions"),
        sa.ForeignKeyConstraint(
            ["asset_id"],
            ["assets.asset_id"],
            name="fk_model_predictions_asset_id_assets",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "ml_risk_probability BETWEEN 0 AND 1",
            name="ck_model_predictions_probability_range",
        ),
        sa.CheckConstraint(
            "ml_risk_rank IS NULL OR ml_risk_rank >= 1",
            name="ck_model_predictions_rank_positive",
        ),
        sa.UniqueConstraint(
            "asset_id",
            "as_of_date",
            "model_name",
            "model_version",
            name="uq_model_predictions_asset_date_model",
        ),
    )
    op.create_index("ix_model_predictions_asset_id", "model_predictions", ["asset_id"])
    op.create_index(
        "ix_model_predictions_as_of_date", "model_predictions", ["as_of_date"]
    )
    op.create_index(
        "ix_model_predictions_model_name", "model_predictions", ["model_name"]
    )
    op.create_index(
        "ix_model_predictions_model_version", "model_predictions", ["model_version"]
    )
    op.create_index(
        "ix_model_predictions_probability", "model_predictions", ["ml_risk_probability"]
    )
    op.create_index("ix_model_predictions_rank", "model_predictions", ["ml_risk_rank"])


def downgrade() -> None:
    """Drop tables in reverse dependency order.

    The ``postgis`` extension is intentionally left installed; uninstalling
    it would break any other schema sharing the database.
    """
    op.drop_table("model_predictions")
    op.drop_table("model_training_data")
    op.drop_table("payout_results")
    op.drop_table("simulation_runs")
    op.drop_table("asset_risk_scores")
    op.drop_table("rainfall_features")
    op.drop_table("asset_station_mapping")
    op.drop_table("rainfall_observations")
    op.drop_table("assets")
    op.drop_table("rainfall_stations")
    op.drop_table("lga_boundaries")
