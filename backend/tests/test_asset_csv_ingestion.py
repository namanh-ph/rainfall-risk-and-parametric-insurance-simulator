"""Tests for the static asset CSV loader"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

import pytest
from geoalchemy2.elements import WKTElement
from pydantic import ValidationError

from src.db.models import Asset
from src.ingestion.assets import (
    load_static_assets_to_db,
    project_asset_record_for_db,
    read_static_assets_csv,
    validate_static_asset_records,
)


def _valid_record(asset_id: str = "VIC0001", **overrides: Any) -> dict[str, Any]:
    rec: dict[str, Any] = {
        "asset_id": asset_id,
        "business_type": "cafe",
        "industry": "hospitality",
        "postcode": "Richmond",
        "latitude": -37.82,
        "longitude": 144.99,
        "asset_value": 750_000,
        "annual_revenue": 380_000,
        "coverage_limit": 80_000,
        # extra columns from the static CSV; must pass through validation
        "stock_value": 5000,
        "policy_excess": 1000,
        "coverage_band": "basic",
    }
    rec.update(overrides)
    return rec


def _write_csv(tmp_path: Path, rows: list[dict[str, Any]]) -> Path:
    target = tmp_path / "assets.csv"
    if not rows:
        target.write_text("asset_id,business_type,industry,postcode,latitude,longitude,asset_value,annual_revenue,coverage_limit\n", encoding="utf-8")
        return target
    with target.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    return target


class _FakeResult:
    def __init__(self, rows: list[tuple] | None = None) -> None:
        self._rows = rows or []

    def all(self) -> list[tuple]:
        return self._rows


class FakeSession:
    def __init__(self, existing_ids: set[str] | None = None) -> None:
        self.added: list[Asset] = []
        self.committed = False
        self.rolled_back = False
        self.deletes: list[Any] = []
        self._existing_ids = set(existing_ids or ())

    def execute(self, statement: Any) -> _FakeResult:
        compiled = str(statement)
        if compiled.lower().startswith("select"):
            return _FakeResult([(asset_id,) for asset_id in self._existing_ids])
        if compiled.lower().startswith("delete"):
            self.deletes.append(statement)
            return _FakeResult()
        return _FakeResult()

    def add_all(self, objs: list[Asset]) -> None:
        self.added.extend(objs)

    def commit(self) -> None:
        self.committed = True

    def rollback(self) -> None:
        self.rolled_back = True

    def close(self) -> None:  # pragma: no cover
        pass


def test_read_static_assets_csv_returns_rows(tmp_path: Path) -> None:
    csv_path = _write_csv(tmp_path, [_valid_record("VIC0001"), _valid_record("VIC0002")])
    rows = read_static_assets_csv(csv_path)
    assert len(rows) == 2
    assert rows[0]["asset_id"] == "VIC0001"


def test_read_static_assets_csv_missing_file() -> None:
    with pytest.raises(FileNotFoundError):
        read_static_assets_csv("does/not/exist.csv")


def test_read_static_assets_csv_missing_required_columns(tmp_path: Path) -> None:
    csv_path = tmp_path / "bad.csv"
    csv_path.write_text("asset_id,postcode\nVIC0001,Richmond\n", encoding="utf-8")
    with pytest.raises(ValueError, match="missing required columns"):
        read_static_assets_csv(csv_path)


def test_read_static_assets_csv_against_committed_dataset() -> None:
    rows = read_static_assets_csv(Path(__file__).parents[2] / "data" / "assets.csv")
    assert len(rows) == 4986
    assert rows[0]["asset_id"] == "VIC0001"
    assert rows[-1]["asset_id"] == "VIC4986"


def test_validate_accepts_valid_records_with_extra_columns() -> None:
    out = validate_static_asset_records([_valid_record("VIC0001"), _valid_record("VIC0002")])
    assert len(out) == 2
    assert "policy_excess" in out[0]  # extras preserved


def test_validate_rejects_missing_canonical_field() -> None:
    rec = _valid_record()
    rec.pop("industry")
    with pytest.raises(ValidationError):
        validate_static_asset_records([rec])


def test_validate_rejects_duplicate_asset_ids() -> None:
    with pytest.raises(ValueError, match="Duplicate asset_id"):
        validate_static_asset_records([_valid_record("VIC0001"), _valid_record("VIC0001")])


@pytest.mark.parametrize("lat", [-50.0, -33.0, 0.0, 10.0])
def test_validate_rejects_invalid_latitude(lat: float) -> None:
    with pytest.raises(ValidationError):
        validate_static_asset_records([_valid_record(latitude=lat)])


@pytest.mark.parametrize("lon", [-200.0, 100.0, 200.0])
def test_validate_rejects_invalid_longitude(lon: float) -> None:
    with pytest.raises(ValidationError):
        validate_static_asset_records([_valid_record(longitude=lon)])


def test_validate_rejects_coverage_above_asset_value() -> None:
    rec = _valid_record(asset_value=100_000, coverage_limit=200_000)
    with pytest.raises(ValidationError):
        validate_static_asset_records([rec])


def test_validate_rejects_negative_asset_value() -> None:
    with pytest.raises(ValidationError):
        validate_static_asset_records([_valid_record(asset_value=-100)])


def test_validate_handles_blank_annual_revenue() -> None:
    out = validate_static_asset_records([_valid_record(annual_revenue="")])
    assert out[0]["annual_revenue"] is None


def test_project_returns_only_db_supported_fields_plus_geom() -> None:
    rec = _valid_record()
    projected = project_asset_record_for_db(rec)
    expected_keys = {
        "asset_id",
        "business_type",
        "industry",
        "postcode",
        "latitude",
        "longitude",
        "asset_value",
        "annual_revenue",
        "coverage_limit",
        "geom",
    }
    assert set(projected.keys()) == expected_keys
    # `lga_code` is populated by the asset-to-LGA join, not here
    assert "lga_code" not in projected
    # CSV-only fields must not survive projection
    for extra in ("stock_value", "policy_excess", "coverage_band"):
        assert extra not in projected


def test_project_geometry_uses_lon_lat_order_and_srid_4326() -> None:
    rec = _valid_record(latitude=-37.8136, longitude=144.9631)
    projected = project_asset_record_for_db(rec)
    geom = projected["geom"]
    assert isinstance(geom, WKTElement)
    assert geom.data == "POINT(144.9631 -37.8136)"
    assert geom.srid == 4326


def test_load_inserts_all_when_db_empty(tmp_path: Path) -> None:
    csv_path = _write_csv(tmp_path, [_valid_record("VIC0001"), _valid_record("VIC0002")])
    session = FakeSession()
    inserted = load_static_assets_to_db(csv_path, session)
    assert inserted == 2
    assert len(session.added) == 2
    assert session.committed is True
    assert session.rolled_back is False


def test_load_skips_existing_when_replace_existing_false(tmp_path: Path) -> None:
    csv_path = _write_csv(
        tmp_path,
        [_valid_record("VIC0001"), _valid_record("VIC0002"), _valid_record("VIC0003")],
    )
    session = FakeSession(existing_ids={"VIC0002"})
    inserted = load_static_assets_to_db(csv_path, session)
    assert inserted == 2
    assert {a.asset_id for a in session.added} == {"VIC0001", "VIC0003"}


def test_load_replaces_existing_when_flag_true(tmp_path: Path) -> None:
    csv_path = _write_csv(tmp_path, [_valid_record("VIC0001"), _valid_record("VIC0002")])
    session = FakeSession(existing_ids={"VIC0001"})
    inserted = load_static_assets_to_db(csv_path, session, replace_existing=True)
    assert inserted == 2
    assert len(session.deletes) == 1
    assert session.committed is True


def test_load_validates_before_insertion(tmp_path: Path) -> None:
    bad = _valid_record(asset_value=-1)
    csv_path = _write_csv(tmp_path, [bad])
    session = FakeSession()
    with pytest.raises(ValidationError):
        load_static_assets_to_db(csv_path, session)
    assert session.committed is False
    assert session.added == []


def test_load_rolls_back_on_failure(tmp_path: Path) -> None:
    csv_path = _write_csv(tmp_path, [_valid_record("VIC0001")])

    class ExplodingSession(FakeSession):
        def add_all(self, objs: list[Asset]) -> None:
            raise RuntimeError("simulated DB error")

    session = ExplodingSession()
    with pytest.raises(RuntimeError):
        load_static_assets_to_db(csv_path, session)
    assert session.rolled_back is True
    assert session.committed is False
