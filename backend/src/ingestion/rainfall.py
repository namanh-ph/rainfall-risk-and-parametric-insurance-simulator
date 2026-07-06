"""Rainfall station and observation ingestion.

Reads station and daily observation CSVs under ``data/`` and loads them
into the ``rainfall_stations`` and ``rainfall_observations`` tables.
This module owns ingestion only — feature engineering, percentiles, and
risk scoring live downstream §3.
"""

from __future__ import annotations

import csv
import logging
from collections.abc import Iterable, Sequence
from datetime import date
from pathlib import Path
from typing import Any

from geoalchemy2.elements import WKTElement
from sqlalchemy import delete, select, tuple_
from sqlalchemy.orm import Session

from src.db.models import RainfallObservation, RainfallStation
from src.domain.constants import DEFAULT_SRID
from src.schemas.rainfall import (
    RainfallObservationCreate,
    RainfallObservationCsvRecord,
    RainfallStationCreate,
    RainfallStationCsvRecord,
)

logger = logging.getLogger(__name__)

DEFAULT_STATION_CSV = Path("../data/rainfall_stations.csv")
DEFAULT_OBSERVATION_CSV = Path("../data/rainfall_observations.csv")


def read_rainfall_stations_csv(input_path: str | Path) -> list[dict[str, Any]]:
    """Read a station CSV file. Required columns mirror ``RainfallStationCreate``."""
    path = Path(input_path)
    if not path.is_file():
        raise FileNotFoundError(f"Rainfall stations CSV not found: {path}")
    with path.open(encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        if reader.fieldnames is None:
            raise ValueError(f"CSV is empty or has no header: {path}")
        return list(reader)


def validate_rainfall_station_records(
    records: Iterable[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Validate stations through ``RainfallStationCsvRecord`` + uniqueness."""
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for record in records:
        validated = RainfallStationCsvRecord.model_validate(record)
        if validated.station_id in seen:
            raise ValueError(f"Duplicate station_id in input: {validated.station_id}")
        seen.add(validated.station_id)
        out.append(validated.model_dump())
    return out


def _station_to_orm(record: dict[str, Any]) -> RainfallStation:
    insert = RainfallStationCreate.model_validate(record)
    geom = WKTElement(
        f"POINT({insert.longitude} {insert.latitude})", srid=DEFAULT_SRID
    )
    return RainfallStation(
        station_id=insert.station_id,
        station_name=insert.station_name,
        latitude=insert.latitude,
        longitude=insert.longitude,
        elevation_m=insert.elevation_m,
        data_source=insert.data_source,
        geom=geom,
    )


def load_rainfall_stations_to_db(
    records: Sequence[dict[str, Any]],
    db: Session,
    replace_existing: bool = False,
) -> int:
    """Insert rainfall station rows, skipping or replacing duplicates."""
    if not records:
        return 0
    validated = validate_rainfall_station_records(records)
    incoming_ids = [r["station_id"] for r in validated]

    try:
        if replace_existing:
            db.execute(
                delete(RainfallStation).where(
                    RainfallStation.station_id.in_(incoming_ids)
                )
            )
            to_insert = validated
        else:
            existing_rows = db.execute(
                select(RainfallStation.station_id).where(
                    RainfallStation.station_id.in_(incoming_ids)
                )
            ).all()
            existing_ids = {row[0] for row in existing_rows}
            if existing_ids:
                logger.warning(
                    "Skipping %d existing rainfall_station rows", len(existing_ids)
                )
            to_insert = [r for r in validated if r["station_id"] not in existing_ids]

        orm_rows = [_station_to_orm(r) for r in to_insert]
        if orm_rows:
            db.add_all(orm_rows)
        db.commit()
        return len(orm_rows)
    except Exception:
        db.rollback()
        raise


def read_rainfall_observations_csv(input_path: str | Path) -> list[dict[str, Any]]:
    """Read an observation CSV file."""
    path = Path(input_path)
    if not path.is_file():
        raise FileNotFoundError(f"Rainfall observations CSV not found: {path}")
    with path.open(encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        if reader.fieldnames is None:
            raise ValueError(f"CSV is empty or has no header: {path}")
        return list(reader)


def validate_rainfall_observation_records(
    records: Iterable[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Validate observations + reject duplicate (station_id, date) pairs."""
    seen: set[tuple[str, date]] = set()
    out: list[dict[str, Any]] = []
    for record in records:
        validated = RainfallObservationCsvRecord.model_validate(record)
        key = (validated.station_id, validated.observation_date)
        if key in seen:
            raise ValueError(
                f"Duplicate (station_id, observation_date) in input: {key}"
            )
        seen.add(key)
        out.append(validated.model_dump())
    return out


def _observation_to_orm(record: dict[str, Any]) -> RainfallObservation:
    insert = RainfallObservationCreate.model_validate(record)
    return RainfallObservation(
        station_id=insert.station_id,
        observation_date=insert.observation_date,
        rainfall_mm=insert.rainfall_mm,
        quality_flag=insert.quality_flag,
    )


def load_rainfall_observations_to_db(
    records: Sequence[dict[str, Any]],
    db: Session,
    replace_existing: bool = False,
) -> int:
    """Insert observations, skipping or replacing duplicate station-date pairs."""
    if not records:
        return 0
    validated = validate_rainfall_observation_records(records)
    keys = [(r["station_id"], r["observation_date"]) for r in validated]

    try:
        if replace_existing:
            db.execute(
                delete(RainfallObservation).where(
                    tuple_(
                        RainfallObservation.station_id,
                        RainfallObservation.observation_date,
                    ).in_(keys)
                )
            )
            to_insert = validated
        else:
            existing_rows = db.execute(
                select(
                    RainfallObservation.station_id,
                    RainfallObservation.observation_date,
                ).where(
                    tuple_(
                        RainfallObservation.station_id,
                        RainfallObservation.observation_date,
                    ).in_(keys)
                )
            ).all()
            existing_keys = {(row[0], row[1]) for row in existing_rows}
            if existing_keys:
                logger.warning(
                    "Skipping %d existing rainfall_observation rows",
                    len(existing_keys),
                )
            to_insert = [
                r
                for r in validated
                if (r["station_id"], r["observation_date"]) not in existing_keys
            ]

        orm_rows = [_observation_to_orm(r) for r in to_insert]
        if orm_rows:
            db.add_all(orm_rows)
        db.commit()
        return len(orm_rows)
    except Exception:
        db.rollback()
        raise


__all__ = [
    "DEFAULT_OBSERVATION_CSV",
    "DEFAULT_STATION_CSV",
    "load_rainfall_observations_to_db",
    "load_rainfall_stations_to_db",
    "read_rainfall_observations_csv",
    "read_rainfall_stations_csv",
    "validate_rainfall_observation_records",
    "validate_rainfall_station_records",
]
