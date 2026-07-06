"""Persistence layer: ORM base, sessions, repositories, migrations helpers.

Importing the ORM models from this package registers them on
``Base.metadata`` so that Alembic ``--autogenerate`` can discover them
"""

from src.db.base import Base, ReprMixin, TimestampMixin
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
from src.db.session import SessionLocal, create_engine_from_settings, get_db

__all__ = [
    "Asset",
    "AssetRiskScore",
    "AssetStationMapping",
    "Base",
    "LgaBoundary",
    "ModelPrediction",
    "ModelTrainingData",
    "PayoutResult",
    "RainfallFeature",
    "RainfallObservation",
    "RainfallStation",
    "ReprMixin",
    "SessionLocal",
    "SimulationRun",
    "TimestampMixin",
    "create_engine_from_settings",
    "get_db",
]
