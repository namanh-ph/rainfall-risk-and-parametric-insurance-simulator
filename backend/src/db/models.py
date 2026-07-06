"""SQLAlchemy ORM models. Any column change here needs a matching Alembic migration."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from geoalchemy2 import Geometry
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.base import Base, ReprMixin, TimestampMixin
from src.domain.constants import (
    DEFAULT_SRID,
    RISK_BANDS,
    STATION_CONFIDENCE_FLOOR,
    TRIGGER_STATUSES,
)


def _risk_band_check(column: str, *, allow_null: bool = False) -> str:
    """Build the CHECK clause for a risk-band column."""
    in_list = ", ".join(f"'{band}'" for band in RISK_BANDS)
    if allow_null:
        return f"{column} IS NULL OR {column} IN ({in_list})"
    return f"{column} IN ({in_list})"


def _trigger_status_check(column: str) -> str:
    in_list = ", ".join(f"'{status}'" for status in TRIGGER_STATUSES)
    return f"{column} IN ({in_list})"


class Asset(Base, TimestampMixin, ReprMixin):
    __tablename__ = "assets"

    asset_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    business_type: Mapped[str] = mapped_column(String(64), nullable=False)
    industry: Mapped[str] = mapped_column(String(128), nullable=False)
    postcode: Mapped[str] = mapped_column(String(128), nullable=False)
    lga_code: Mapped[str | None] = mapped_column(
        String(16),
        ForeignKey("lga_boundaries.lga_code", ondelete="RESTRICT"),
        nullable=True,
    )

    latitude: Mapped[float] = mapped_column(Numeric(9, 6), nullable=False)
    longitude: Mapped[float] = mapped_column(Numeric(9, 6), nullable=False)

    asset_value: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    annual_revenue: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    coverage_limit: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)

    geom: Mapped[object] = mapped_column(
        Geometry(geometry_type="POINT", srid=DEFAULT_SRID, spatial_index=False),
        nullable=False,
    )

    rainfall_features: Mapped[list[RainfallFeature]] = relationship(
        back_populates="asset", cascade="all, delete-orphan", passive_deletes=True
    )
    risk_scores: Mapped[list[AssetRiskScore]] = relationship(
        back_populates="asset", cascade="all, delete-orphan", passive_deletes=True
    )
    station_mapping: Mapped[AssetStationMapping | None] = relationship(
        back_populates="asset",
        uselist=False,
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    payout_results: Mapped[list[PayoutResult]] = relationship(
        back_populates="asset", cascade="all, delete-orphan", passive_deletes=True
    )
    training_rows: Mapped[list[ModelTrainingData]] = relationship(
        back_populates="asset", cascade="all, delete-orphan", passive_deletes=True
    )
    predictions: Mapped[list[ModelPrediction]] = relationship(
        back_populates="asset", cascade="all, delete-orphan", passive_deletes=True
    )

    __table_args__ = (
        CheckConstraint("asset_value >= 0", name="ck_assets_asset_value_non_negative"),
        CheckConstraint(
            "annual_revenue IS NULL OR annual_revenue >= 0",
            name="ck_assets_annual_revenue_non_negative",
        ),
        CheckConstraint("coverage_limit >= 0", name="ck_assets_coverage_limit_non_negative"),
        CheckConstraint("latitude BETWEEN -90 AND 90", name="ck_assets_latitude_range"),
        CheckConstraint("longitude BETWEEN -180 AND 180", name="ck_assets_longitude_range"),
        Index("ix_assets_geom", "geom", postgresql_using="gist"),
        Index("ix_assets_postcode", "postcode"),
        Index("ix_assets_industry", "industry"),
        Index("ix_assets_lga_code", "lga_code"),
    )


class RainfallStation(Base, TimestampMixin, ReprMixin):
    __tablename__ = "rainfall_stations"

    station_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    station_name: Mapped[str] = mapped_column(String(255), nullable=False)
    latitude: Mapped[float] = mapped_column(Numeric(9, 6), nullable=False)
    longitude: Mapped[float] = mapped_column(Numeric(9, 6), nullable=False)
    elevation_m: Mapped[float | None] = mapped_column(Numeric(7, 2), nullable=True)

    geom: Mapped[object] = mapped_column(
        Geometry(geometry_type="POINT", srid=DEFAULT_SRID, spatial_index=False),
        nullable=False,
    )

    data_source: Mapped[str] = mapped_column(String(64), nullable=False, default="bom")

    observations: Mapped[list[RainfallObservation]] = relationship(
        back_populates="station", cascade="all, delete-orphan", passive_deletes=True
    )
    rainfall_features: Mapped[list[RainfallFeature]] = relationship(back_populates="station")
    asset_mappings: Mapped[list[AssetStationMapping]] = relationship(back_populates="station")

    __table_args__ = (
        CheckConstraint(
            "latitude BETWEEN -90 AND 90", name="ck_rainfall_stations_latitude_range"
        ),
        CheckConstraint(
            "longitude BETWEEN -180 AND 180", name="ck_rainfall_stations_longitude_range"
        ),
        Index("ix_rainfall_stations_geom", "geom", postgresql_using="gist"),
        Index("ix_rainfall_stations_station_name", "station_name"),
        Index("ix_rainfall_stations_data_source", "data_source"),
    )


class RainfallObservation(Base, TimestampMixin, ReprMixin):
    __tablename__ = "rainfall_observations"

    observation_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    station_id: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("rainfall_stations.station_id", ondelete="CASCADE"),
        nullable=False,
    )
    observation_date: Mapped[date] = mapped_column(Date, nullable=False)
    rainfall_mm: Mapped[Decimal] = mapped_column(Numeric(7, 2), nullable=False)
    quality_flag: Mapped[str | None] = mapped_column(String(8), nullable=True)

    station: Mapped[RainfallStation] = relationship(back_populates="observations")

    __table_args__ = (
        CheckConstraint(
            "rainfall_mm >= 0", name="ck_rainfall_observations_rainfall_mm_non_negative"
        ),
        UniqueConstraint(
            "station_id", "observation_date", name="uq_rainfall_observations_station_date"
        ),
        Index("ix_rainfall_observations_station_id", "station_id"),
        Index("ix_rainfall_observations_observation_date", "observation_date"),
        Index(
            "ix_rainfall_observations_station_date_combo", "station_id", "observation_date"
        ),
    )


class AssetStationMapping(Base, TimestampMixin, ReprMixin):
    __tablename__ = "asset_station_mapping"

    asset_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("assets.asset_id", ondelete="CASCADE"),
        primary_key=True,
    )
    station_id: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("rainfall_stations.station_id", ondelete="RESTRICT"),
        nullable=False,
    )
    station_distance_km: Mapped[Decimal] = mapped_column(Numeric(8, 3), nullable=False)
    station_confidence_weight: Mapped[Decimal] = mapped_column(Numeric(4, 3), nullable=False)
    matched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    asset: Mapped[Asset] = relationship(back_populates="station_mapping")
    station: Mapped[RainfallStation] = relationship(back_populates="asset_mappings")

    __table_args__ = (
        CheckConstraint(
            "station_distance_km >= 0",
            name="ck_asset_station_mapping_distance_non_negative",
        ),
        CheckConstraint(
            f"station_confidence_weight BETWEEN {STATION_CONFIDENCE_FLOOR} AND 1.00",
            name="ck_asset_station_mapping_confidence_range",
        ),
        Index("ix_asset_station_mapping_station_id", "station_id"),
        Index("ix_asset_station_mapping_distance", "station_distance_km"),
    )


class LgaBoundary(Base, TimestampMixin, ReprMixin):
    __tablename__ = "lga_boundaries"

    lga_code: Mapped[str] = mapped_column(String(16), primary_key=True)
    lga_name: Mapped[str] = mapped_column(String(128), nullable=False)
    state: Mapped[str] = mapped_column(String(8), nullable=False, default="VIC")
    geom: Mapped[object] = mapped_column(
        Geometry(geometry_type="MULTIPOLYGON", srid=DEFAULT_SRID, spatial_index=False),
        nullable=False,
    )
    data_source: Mapped[str] = mapped_column(String(64), nullable=False, default="abs")

    __table_args__ = (
        UniqueConstraint("lga_name", "state", name="uq_lga_boundaries_name_state"),
        Index("ix_lga_boundaries_geom", "geom", postgresql_using="gist"),
        Index("ix_lga_boundaries_lga_name", "lga_name"),
        Index("ix_lga_boundaries_state", "state"),
    )


class RainfallFeature(Base, TimestampMixin, ReprMixin):
    __tablename__ = "rainfall_features"

    feature_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    asset_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("assets.asset_id", ondelete="CASCADE"),
        nullable=False,
    )
    station_id: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("rainfall_stations.station_id", ondelete="RESTRICT"),
        nullable=False,
    )
    as_of_date: Mapped[date] = mapped_column(Date, nullable=False)

    rainfall_1d_mm: Mapped[Decimal] = mapped_column(Numeric(7, 2), nullable=False)
    rainfall_3d_mm: Mapped[Decimal] = mapped_column(Numeric(7, 2), nullable=False)
    rainfall_7d_mm: Mapped[Decimal] = mapped_column(Numeric(7, 2), nullable=False)
    rainfall_30d_mm: Mapped[Decimal] = mapped_column(Numeric(7, 2), nullable=False)

    rainfall_p95_station: Mapped[Decimal | None] = mapped_column(Numeric(7, 2), nullable=True)
    rainfall_p99_station: Mapped[Decimal | None] = mapped_column(Numeric(7, 2), nullable=True)
    rainfall_percentile: Mapped[Decimal | None] = mapped_column(Numeric(6, 4), nullable=True)
    max_365d_rainfall_mm: Mapped[Decimal | None] = mapped_column(Numeric(7, 2), nullable=True)
    days_above_p95_365d: Mapped[int | None] = mapped_column(Integer, nullable=True)

    extreme_rainfall_flag: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )

    asset: Mapped[Asset] = relationship(back_populates="rainfall_features")
    station: Mapped[RainfallStation] = relationship(back_populates="rainfall_features")

    __table_args__ = (
        CheckConstraint(
            "rainfall_1d_mm >= 0", name="ck_rainfall_features_rainfall_1d_non_negative"
        ),
        CheckConstraint(
            "rainfall_3d_mm >= 0", name="ck_rainfall_features_rainfall_3d_non_negative"
        ),
        CheckConstraint(
            "rainfall_7d_mm >= 0", name="ck_rainfall_features_rainfall_7d_non_negative"
        ),
        CheckConstraint(
            "rainfall_30d_mm >= 0",
            name="ck_rainfall_features_rainfall_30d_non_negative",
        ),
        CheckConstraint(
            "rainfall_p95_station IS NULL OR rainfall_p95_station >= 0",
            name="ck_rainfall_features_p95_non_negative",
        ),
        CheckConstraint(
            "rainfall_p99_station IS NULL OR rainfall_p99_station >= 0",
            name="ck_rainfall_features_p99_non_negative",
        ),
        CheckConstraint(
            "max_365d_rainfall_mm IS NULL OR max_365d_rainfall_mm >= 0",
            name="ck_rainfall_features_max_365d_non_negative",
        ),
        CheckConstraint(
            "rainfall_percentile IS NULL OR rainfall_percentile BETWEEN 0 AND 1",
            name="ck_rainfall_features_percentile_range",
        ),
        CheckConstraint(
            "days_above_p95_365d IS NULL OR days_above_p95_365d >= 0",
            name="ck_rainfall_features_days_above_p95_non_negative",
        ),
        UniqueConstraint("asset_id", "as_of_date", name="uq_rainfall_features_asset_date"),
        Index("ix_rainfall_features_asset_id", "asset_id"),
        Index("ix_rainfall_features_station_id", "station_id"),
        Index("ix_rainfall_features_as_of_date", "as_of_date"),
        Index("ix_rainfall_features_extreme_flag", "extreme_rainfall_flag"),
    )


class AssetRiskScore(Base, TimestampMixin, ReprMixin):
    __tablename__ = "asset_risk_scores"

    risk_score_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    asset_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("assets.asset_id", ondelete="CASCADE"),
        nullable=False,
    )
    as_of_date: Mapped[date] = mapped_column(Date, nullable=False)

    rainfall_extreme_score: Mapped[Decimal] = mapped_column(Numeric(6, 2), nullable=False)
    exposure_weight: Mapped[Decimal] = mapped_column(Numeric(5, 3), nullable=False)
    vulnerability_weight: Mapped[Decimal] = mapped_column(Numeric(5, 3), nullable=False)
    station_confidence_weight: Mapped[Decimal] = mapped_column(Numeric(4, 3), nullable=False)

    raw_score: Mapped[Decimal] = mapped_column(Numeric(8, 3), nullable=False)
    risk_score: Mapped[Decimal] = mapped_column(Numeric(6, 2), nullable=False)
    risk_band: Mapped[str] = mapped_column(String(16), nullable=False)

    asset: Mapped[Asset] = relationship(back_populates="risk_scores")

    __table_args__ = (
        CheckConstraint(
            "rainfall_extreme_score BETWEEN 0 AND 100",
            name="ck_asset_risk_scores_extreme_range",
        ),
        CheckConstraint("exposure_weight > 0", name="ck_asset_risk_scores_exposure_positive"),
        CheckConstraint(
            "vulnerability_weight > 0",
            name="ck_asset_risk_scores_vulnerability_positive",
        ),
        CheckConstraint(
            f"station_confidence_weight BETWEEN {STATION_CONFIDENCE_FLOOR} AND 1.00",
            name="ck_asset_risk_scores_confidence_range",
        ),
        CheckConstraint(
            "risk_score BETWEEN 0 AND 100", name="ck_asset_risk_scores_score_range"
        ),
        CheckConstraint(_risk_band_check("risk_band"), name="ck_asset_risk_scores_band"),
        UniqueConstraint("asset_id", "as_of_date", name="uq_asset_risk_scores_asset_date"),
        Index("ix_asset_risk_scores_asset_id", "asset_id"),
        Index("ix_asset_risk_scores_as_of_date", "as_of_date"),
        Index("ix_asset_risk_scores_risk_band", "risk_band"),
        Index("ix_asset_risk_scores_risk_score", "risk_score"),
    )


class SimulationRun(Base, TimestampMixin, ReprMixin):
    __tablename__ = "simulation_runs"

    simulation_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    simulation_name: Mapped[str] = mapped_column(String(128), nullable=False)
    as_of_date: Mapped[date] = mapped_column(Date, nullable=False)
    threshold_config: Mapped[dict] = mapped_column(JSONB, nullable=False)
    coverage_multiplier: Mapped[Decimal] = mapped_column(
        Numeric(5, 3), nullable=False, default=Decimal("1.0"), server_default="1.0"
    )

    payout_results: Mapped[list[PayoutResult]] = relationship(
        back_populates="simulation", cascade="all, delete-orphan", passive_deletes=True
    )

    __table_args__ = (
        CheckConstraint(
            "coverage_multiplier > 0",
            name="ck_simulation_runs_coverage_multiplier_positive",
        ),
        Index("ix_simulation_runs_as_of_date", "as_of_date"),
        Index("ix_simulation_runs_simulation_name", "simulation_name"),
    )


class PayoutResult(Base, TimestampMixin, ReprMixin):
    __tablename__ = "payout_results"

    payout_result_id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )
    simulation_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("simulation_runs.simulation_id", ondelete="CASCADE"),
        nullable=False,
    )
    asset_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("assets.asset_id", ondelete="CASCADE"),
        nullable=False,
    )
    rainfall_3d_mm: Mapped[Decimal] = mapped_column(Numeric(7, 2), nullable=False)
    trigger_status: Mapped[str] = mapped_column(String(32), nullable=False)
    payout_rate: Mapped[Decimal] = mapped_column(Numeric(4, 3), nullable=False)
    coverage_limit: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    estimated_payout: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    risk_band: Mapped[str | None] = mapped_column(String(16), nullable=True)

    simulation: Mapped[SimulationRun] = relationship(back_populates="payout_results")
    asset: Mapped[Asset] = relationship(back_populates="payout_results")

    __table_args__ = (
        CheckConstraint(
            "rainfall_3d_mm >= 0", name="ck_payout_results_rainfall_3d_non_negative"
        ),
        CheckConstraint(
            _trigger_status_check("trigger_status"),
            name="ck_payout_results_trigger_status",
        ),
        CheckConstraint(
            "payout_rate BETWEEN 0 AND 1", name="ck_payout_results_payout_rate_range"
        ),
        CheckConstraint(
            "coverage_limit >= 0", name="ck_payout_results_coverage_limit_non_negative"
        ),
        CheckConstraint(
            "estimated_payout >= 0",
            name="ck_payout_results_estimated_payout_non_negative",
        ),
        CheckConstraint(
            _risk_band_check("risk_band", allow_null=True),
            name="ck_payout_results_risk_band",
        ),
        UniqueConstraint(
            "simulation_id", "asset_id", name="uq_payout_results_simulation_asset"
        ),
        Index("ix_payout_results_simulation_id", "simulation_id"),
        Index("ix_payout_results_asset_id", "asset_id"),
        Index("ix_payout_results_trigger_status", "trigger_status"),
        Index("ix_payout_results_estimated_payout", "estimated_payout"),
    )


class ModelTrainingData(Base, TimestampMixin, ReprMixin):
    __tablename__ = "model_training_data"

    training_row_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    asset_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("assets.asset_id", ondelete="CASCADE"),
        nullable=False,
    )
    as_of_date: Mapped[date] = mapped_column(Date, nullable=False)
    feature_version: Mapped[str] = mapped_column(String(32), nullable=False)
    target_extreme_rainfall_event: Mapped[bool] = mapped_column(Boolean, nullable=False)
    engineered_features_json: Mapped[dict] = mapped_column(JSONB, nullable=False)

    asset: Mapped[Asset] = relationship(back_populates="training_rows")

    __table_args__ = (
        UniqueConstraint(
            "asset_id",
            "as_of_date",
            "feature_version",
            name="uq_model_training_data_asset_date_version",
        ),
        Index("ix_model_training_data_asset_id", "asset_id"),
        Index("ix_model_training_data_as_of_date", "as_of_date"),
        Index("ix_model_training_data_feature_version", "feature_version"),
        Index(
            "ix_model_training_data_target_extreme_event",
            "target_extreme_rainfall_event",
        ),
    )


class ModelPrediction(Base, TimestampMixin, ReprMixin):
    __tablename__ = "model_predictions"

    prediction_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    asset_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("assets.asset_id", ondelete="CASCADE"),
        nullable=False,
    )
    as_of_date: Mapped[date] = mapped_column(Date, nullable=False)
    model_name: Mapped[str] = mapped_column(String(128), nullable=False)
    model_version: Mapped[str] = mapped_column(String(64), nullable=False)
    ml_risk_probability: Mapped[Decimal] = mapped_column(Numeric(6, 5), nullable=False)
    ml_risk_rank: Mapped[int | None] = mapped_column(Integer, nullable=True)
    top_risk_driver: Mapped[str | None] = mapped_column(String(128), nullable=True)

    asset: Mapped[Asset] = relationship(back_populates="predictions")

    __table_args__ = (
        CheckConstraint(
            "ml_risk_probability BETWEEN 0 AND 1",
            name="ck_model_predictions_probability_range",
        ),
        CheckConstraint(
            "ml_risk_rank IS NULL OR ml_risk_rank >= 1",
            name="ck_model_predictions_rank_positive",
        ),
        UniqueConstraint(
            "asset_id",
            "as_of_date",
            "model_name",
            "model_version",
            name="uq_model_predictions_asset_date_model",
        ),
        Index("ix_model_predictions_asset_id", "asset_id"),
        Index("ix_model_predictions_as_of_date", "as_of_date"),
        Index("ix_model_predictions_model_name", "model_name"),
        Index("ix_model_predictions_model_version", "model_version"),
        Index("ix_model_predictions_probability", "ml_risk_probability"),
        Index("ix_model_predictions_rank", "ml_risk_rank"),
    )


__all__ = [
    "Asset",
    "AssetRiskScore",
    "AssetStationMapping",
    "LgaBoundary",
    "ModelPrediction",
    "ModelTrainingData",
    "PayoutResult",
    "RainfallFeature",
    "RainfallObservation",
    "RainfallStation",
    "SimulationRun",
]
