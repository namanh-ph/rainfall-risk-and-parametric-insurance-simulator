"""Tests for LGA boundary ingestion (file readers, validation, DB load)."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

import pytest
from geoalchemy2.elements import WKTElement
from shapely.geometry import MultiPolygon, Polygon, mapping

from src.db.models import LgaBoundary
from src.ingestion.boundaries import (
    load_lga_boundaries_to_db,
    project_lga_boundary_record_for_db,
    read_lga_boundaries_csv,
    read_lga_boundaries_file,
    read_lga_boundaries_geojson,
    validate_lga_boundary_records,
)

# A small Victoria-plausible square reused across the manual tests
_GOOD_RING = [
    (144.95, -37.85),
    (145.05, -37.85),
    (145.05, -37.75),
    (144.95, -37.75),
    (144.95, -37.85),
]


def _good_polygon() -> Polygon:
    return Polygon(_GOOD_RING)


def _good_record(lga_code: str = "X1", lga_name: str = "Test") -> dict[str, Any]:
    return {
        "lga_code": lga_code,
        "lga_name": lga_name,
        "state": "VIC",
        "data_source": "abs",
        "geometry": _good_polygon(),
    }


class _FakeResult:
    def __init__(self, rows: list[tuple] | None = None) -> None:
        self._rows = rows or []

    def all(self) -> list[tuple]:
        return self._rows


class FakeSession:
    def __init__(self, existing_codes: set[str] | None = None) -> None:
        self.added: list[Any] = []
        self.committed = False
        self.rolled_back = False
        self.deletes: list[Any] = []
        self._existing = set(existing_codes or ())

    def execute(self, statement: Any) -> _FakeResult:
        compiled = str(statement)
        if compiled.lower().startswith("select"):
            return _FakeResult([(code,) for code in self._existing])
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


def test_validate_accepts_well_formed_record() -> None:
    out = validate_lga_boundary_records([_good_record()])
    assert len(out) == 1


def test_validate_rejects_duplicate_lga_codes() -> None:
    a = _good_record("X1", "Test A")
    b = _good_record("X1", "Test B")
    with pytest.raises(ValueError, match="Duplicate lga_code"):
        validate_lga_boundary_records([a, b])


def test_validate_rejects_missing_geometry() -> None:
    record = _good_record()
    record["geometry"] = None
    with pytest.raises(ValueError, match="Missing geometry"):
        validate_lga_boundary_records([record])


def test_validate_rejects_empty_geometry() -> None:
    record = _good_record()
    record["geometry"] = Polygon()
    with pytest.raises(ValueError, match="Empty geometry"):
        validate_lga_boundary_records([record])


def test_validate_rejects_geometry_outside_victoria() -> None:
    record = _good_record()
    record["geometry"] = Polygon(
        [(160.0, -20.0), (161.0, -20.0), (161.0, -19.0), (160.0, -19.0), (160.0, -20.0)]
    )
    with pytest.raises(ValueError, match="outside Victoria"):
        validate_lga_boundary_records([record])


def test_project_returns_only_db_supported_fields_plus_geom() -> None:
    record = _good_record()
    record["extra_column"] = "ignored"
    projected = project_lga_boundary_record_for_db(record)
    assert set(projected.keys()) == {"lga_code", "lga_name", "state", "data_source", "geom"}


def test_project_converts_polygon_to_multipolygon_wkt() -> None:
    projected = project_lga_boundary_record_for_db(_good_record())
    geom = projected["geom"]
    assert isinstance(geom, WKTElement)
    assert geom.data.startswith("MULTIPOLYGON"), geom.data
    assert geom.srid == 4326


def test_project_preserves_multipolygon_input() -> None:
    record = _good_record()
    record["geometry"] = MultiPolygon([_good_polygon()])
    projected = project_lga_boundary_record_for_db(record)
    assert projected["geom"].data.startswith("MULTIPOLYGON")


def test_project_uses_srid_4326() -> None:
    assert project_lga_boundary_record_for_db(_good_record())["geom"].srid == 4326


def test_read_geojson_round_trip(tmp_path: Path) -> None:
    feature = {
        "type": "Feature",
        "properties": {"LGA_CODE_2024": "20660", "LGA_NAME_2024": "Melbourne"},
        "geometry": mapping(_good_polygon()),
    }
    fc = {"type": "FeatureCollection", "features": [feature]}
    path = tmp_path / "vic.geojson"
    path.write_text(json.dumps(fc), encoding="utf-8")

    rows = read_lga_boundaries_geojson(path)
    assert len(rows) == 1
    assert rows[0]["lga_code"] == "20660"
    assert rows[0]["lga_name"] == "Melbourne"
    assert rows[0]["state"] == "VIC"
    assert isinstance(rows[0]["geometry"], (Polygon, MultiPolygon))


def test_read_csv_with_wkt_geometry(tmp_path: Path) -> None:
    path = tmp_path / "vic.csv"
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=["lga_code", "lga_name", "state", "geometry"])
        writer.writeheader()
        writer.writerow(
            {
                "lga_code": "X1",
                "lga_name": "Test",
                "state": "VIC",
                "geometry": _good_polygon().wkt,
            }
        )
    rows = read_lga_boundaries_csv(path)
    assert rows[0]["lga_code"] == "X1"
    assert isinstance(rows[0]["geometry"], (Polygon, MultiPolygon))


def test_read_lga_boundaries_file_dispatches_by_extension(tmp_path: Path) -> None:
    geojson_path = tmp_path / "vic.geojson"
    geojson_path.write_text(
        json.dumps(
            {
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "properties": {"lga_code": "X1", "lga_name": "Test"},
                        "geometry": mapping(_good_polygon()),
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    rows = read_lga_boundaries_file(geojson_path)
    assert rows[0]["lga_code"] == "X1"


def test_read_lga_boundaries_file_unsupported_extension(tmp_path: Path) -> None:
    path = tmp_path / "vic.txt"
    path.write_text("nope", encoding="utf-8")
    with pytest.raises(ValueError, match="Unsupported boundary file extension"):
        read_lga_boundaries_file(path)


def test_read_geojson_missing_file() -> None:
    with pytest.raises(FileNotFoundError):
        read_lga_boundaries_geojson("does/not/exist.geojson")


def _three_records() -> list[dict[str, Any]]:
    return [
        _good_record("X1", "Test A"),
        _good_record("X2", "Test B"),
        _good_record("X3", "Test C"),
    ]


def test_load_inserts_all_when_db_empty() -> None:
    records = _three_records()
    session = FakeSession()
    n = load_lga_boundaries_to_db(records, session)
    assert n == len(records)
    assert session.committed is True
    assert all(isinstance(o, LgaBoundary) for o in session.added)


def test_load_skips_existing_when_replace_false() -> None:
    records = _three_records()
    existing = {records[0]["lga_code"], records[2]["lga_code"]}
    session = FakeSession(existing_codes=existing)
    n = load_lga_boundaries_to_db(records, session)
    assert n == len(records) - 2
    assert {a.lga_code for a in session.added}.isdisjoint(existing)


def test_load_replaces_existing_when_flag_true() -> None:
    records = _three_records()
    existing = {records[0]["lga_code"]}
    session = FakeSession(existing_codes=existing)
    n = load_lga_boundaries_to_db(records, session, replace_existing=True)
    assert n == len(records)
    assert len(session.deletes) == 1
    assert session.committed is True


def test_load_validates_before_insertion() -> None:
    bad = _good_record()
    bad["geometry"] = None
    session = FakeSession()
    with pytest.raises(ValueError):
        load_lga_boundaries_to_db([bad], session)
    assert session.committed is False
    assert session.added == []


def test_load_rolls_back_on_failure() -> None:
    records = _three_records()

    class Boom(FakeSession):
        def add_all(self, objs: list[Any]) -> None:
            raise RuntimeError("boom")

    session = Boom()
    with pytest.raises(RuntimeError):
        load_lga_boundaries_to_db(records, session)
    assert session.rolled_back is True


def test_load_returns_zero_for_empty_input() -> None:
    session = FakeSession()
    assert load_lga_boundaries_to_db([], session) == 0
    assert session.committed is False
