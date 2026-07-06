"""Tests for rainfall station and observation ingestion."""

from __future__ import annotations

import csv
from datetime import date
from pathlib import Path
from typing import Any

import pytest
from geoalchemy2.elements import WKTElement
from pydantic import ValidationError

from src.db.models import RainfallObservation, RainfallStation
from src.ingestion.rainfall import (
    _observation_to_orm,
    _station_to_orm,
    load_rainfall_observations_to_db,
    load_rainfall_stations_to_db,
    read_rainfall_observations_csv,
    read_rainfall_stations_csv,
    validate_rainfall_observation_records,
    validate_rainfall_station_records,
)


def _station_records() -> list[dict[str, Any]]:
    return [
        {
            "station_id": "086282",
            "station_name": "Melbourne Olympic Park",
            "latitude": -37.8255,
            "longitude": 144.9816,
            "elevation_m": 7.5,
            "data_source": "bom",
        },
        {
            "station_id": "087113",
            "station_name": "Avalon Airport",
            "latitude": -38.0394,
            "longitude": 144.4694,
            "elevation_m": 10.6,
            "data_source": "bom",
        },
    ]


def _observation_records() -> list[dict[str, Any]]:
    return [
        {
            "station_id": "086282",
            "observation_date": "2025-01-01",
            "rainfall_mm": 1.2,
            "quality_flag": "Y",
        },
        {
            "station_id": "086282",
            "observation_date": "2025-01-02",
            "rainfall_mm": 0.0,
            "quality_flag": "Y",
        },
        {
            "station_id": "087113",
            "observation_date": "2025-01-01",
            "rainfall_mm": 4.7,
            "quality_flag": "Y",
        },
    ]


class _FakeResult:
    def __init__(self, rows: list[tuple] | None = None) -> None:
        self._rows = rows or []

    def all(self) -> list[tuple]:
        return self._rows


class FakeSession:
    def __init__(self, existing: list[tuple] | None = None) -> None:
        self.added: list[Any] = []
        self.committed = False
        self.rolled_back = False
        self.deletes: list[Any] = []
        self._existing = existing or []

    def execute(self, statement: Any) -> _FakeResult:
        compiled = str(statement)
        if compiled.lower().startswith("select"):
            return _FakeResult(self._existing)
        if compiled.lower().startswith("delete"):
            self.deletes.append(statement)
            return _FakeResult()
        return _FakeResult()

    def add_all(self, objs: list[Any]) -> None:
        self.added.extend(objs)

    def commit(self) -> None:
        self.committed = True

    def rollback(self) -> None:
        self.rolled_back = True

    def close(self) -> None:  # pragma: no cover
        pass


def test_validate_rejects_duplicate_station_ids() -> None:
    stations = _station_records()
    with pytest.raises(ValueError, match="Duplicate station_id"):
        validate_rainfall_station_records([stations[0], stations[0]])


def test_validate_rejects_invalid_station_lat() -> None:
    s = dict(_station_records()[0])
    s["latitude"] = -50.0
    with pytest.raises(ValidationError):
        validate_rainfall_station_records([s])


def test_validate_rejects_duplicate_observation_keys() -> None:
    obs = [
        {"station_id": "086282", "observation_date": "2025-01-01", "rainfall_mm": 1.0, "quality_flag": "Y"},
        {"station_id": "086282", "observation_date": "2025-01-01", "rainfall_mm": 2.0, "quality_flag": "Y"},
    ]
    with pytest.raises(ValueError, match="Duplicate"):
        validate_rainfall_observation_records(obs)


def test_validate_rejects_negative_rainfall() -> None:
    obs = [{"station_id": "086282", "observation_date": "2025-01-01", "rainfall_mm": -5.0, "quality_flag": "Y"}]
    with pytest.raises(ValidationError):
        validate_rainfall_observation_records(obs)


def test_validate_accepts_blank_quality_flag() -> None:
    out = validate_rainfall_observation_records(
        [{"station_id": "086282", "observation_date": "2025-01-01", "rainfall_mm": 0.0, "quality_flag": ""}]
    )
    assert out[0]["quality_flag"] is None


def test_read_rainfall_stations_csv(tmp_path: Path) -> None:
    csv_path = tmp_path / "stations.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=["station_id", "station_name", "latitude", "longitude", "elevation_m", "data_source"],
        )
        writer.writeheader()
        writer.writerow(
            {"station_id": "X1", "station_name": "Test", "latitude": -37.8, "longitude": 144.9, "elevation_m": "10", "data_source": "test"}
        )
    rows = read_rainfall_stations_csv(csv_path)
    assert rows[0]["station_id"] == "X1"


def test_read_rainfall_observations_csv(tmp_path: Path) -> None:
    csv_path = tmp_path / "obs.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(
            fh, fieldnames=["station_id", "observation_date", "rainfall_mm", "quality_flag"]
        )
        writer.writeheader()
        writer.writerow(
            {"station_id": "X1", "observation_date": "2025-01-01", "rainfall_mm": "2.5", "quality_flag": "Y"}
        )
    rows = read_rainfall_observations_csv(csv_path)
    assert rows[0]["station_id"] == "X1"


def test_read_rainfall_stations_csv_missing_file() -> None:
    with pytest.raises(FileNotFoundError):
        read_rainfall_stations_csv("does/not/exist.csv")


def test_station_to_orm_geometry_uses_lon_lat_order_and_srid_4326() -> None:
    s = _station_records()[0]
    orm = _station_to_orm(s)
    assert isinstance(orm.geom, WKTElement)
    assert orm.geom.data == f"POINT({s['longitude']} {s['latitude']})"
    assert orm.geom.srid == 4326


def test_observation_to_orm_returns_observation_row() -> None:
    orm = _observation_to_orm(
        {"station_id": "086282", "observation_date": date(2025, 1, 1), "rainfall_mm": 4.5, "quality_flag": "Y"}
    )
    assert isinstance(orm, RainfallObservation)
    assert orm.station_id == "086282"
    assert orm.rainfall_mm == 4.5


def test_load_rainfall_stations_inserts_all() -> None:
    stations = _station_records()
    session = FakeSession()
    n = load_rainfall_stations_to_db(stations, session)
    assert n == len(stations)
    assert session.committed is True
    assert all(isinstance(o, RainfallStation) for o in session.added)


def test_load_rainfall_stations_skips_existing() -> None:
    stations = _station_records()
    session = FakeSession(existing=[(stations[0]["station_id"],)])
    n = load_rainfall_stations_to_db(stations, session)
    assert n == len(stations) - 1


def test_load_rainfall_stations_replaces_existing_with_flag() -> None:
    stations = _station_records()
    session = FakeSession(existing=[(stations[0]["station_id"],)])
    n = load_rainfall_stations_to_db(stations, session, replace_existing=True)
    assert n == len(stations)
    assert len(session.deletes) == 1


def test_load_rainfall_observations_validates_before_insert() -> None:
    session = FakeSession()
    bad = [{"station_id": "086282", "observation_date": "2025-01-01", "rainfall_mm": -1, "quality_flag": "Y"}]
    with pytest.raises(ValidationError):
        load_rainfall_observations_to_db(bad, session)
    assert session.committed is False
    assert session.added == []


def test_load_rainfall_observations_inserts_batch() -> None:
    obs = _observation_records()
    session = FakeSession()
    n = load_rainfall_observations_to_db(obs, session)
    assert n == len(obs)
    assert session.committed is True


def test_load_rainfall_observations_rolls_back_on_failure() -> None:
    obs = _observation_records()

    class Boom(FakeSession):
        def add_all(self, objs: list[Any]) -> None:
            raise RuntimeError("boom")

    session = Boom()
    with pytest.raises(RuntimeError):
        load_rainfall_observations_to_db(obs, session)
    assert session.rolled_back is True
