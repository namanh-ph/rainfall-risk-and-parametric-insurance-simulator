"""Load Victorian LGA boundary files (GeoJSON / CSV+WKT / Shapefile) into PostGIS."""

from __future__ import annotations

import csv
import json
import logging
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any

from geoalchemy2.elements import WKTElement
from shapely.geometry import MultiPolygon, Polygon, mapping, shape
from shapely.geometry.base import BaseGeometry
from shapely.validation import make_valid
from shapely.wkt import loads as wkt_loads
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from src.db.models import LgaBoundary
from src.domain.constants import DEFAULT_SRID
from src.schemas.boundaries import LgaBoundaryCreate, LgaBoundaryCsvRecord

logger = logging.getLogger(__name__)

DEFAULT_BOUNDARY_FILE = Path("../data/vic_lga_boundaries.geojson")

# Victoria-plausible bounds for geometry sanity checks
VIC_LAT_MIN, VIC_LAT_MAX = -39.3, -33.9
VIC_LON_MIN, VIC_LON_MAX = 140.7, 150.2

_BOUNDS_TOLERANCE = 0.05

# Field-name normalisation: source schemas vary widely
_LGA_CODE_ALIASES = (
    "lga_code",
    "LGA_CODE",
    "LGA_CODE_2024",
    "lga_code_2024",
    "vic_lga_code",
    "VIC_LGA_CODE",
    "code",
    "CODE",
)
_LGA_NAME_ALIASES = (
    "lga_name",
    "LGA_NAME",
    "LGA_NAME_2024",
    "lga_name_2024",
    "vic_lga_name",
    "VIC_LGA_NAME",
    "name",
    "NAME",
)
_STATE_ALIASES = ("state", "STATE", "STATE_NAME")
_DATA_SOURCE_ALIASES = ("data_source", "DATA_SOURCE", "source", "SOURCE")
_GEOMETRY_ALIASES = ("geometry", "geom", "wkt", "WKT", "the_geom")


def _coerce_to_geometry(value: Any) -> BaseGeometry | None:
    """Accept Shapely objects, WKT strings, or GeoJSON-geometry dicts."""
    if value is None:
        return None
    if isinstance(value, BaseGeometry):
        return value
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        return wkt_loads(text)
    if isinstance(value, dict):
        return shape(value)
    raise TypeError(f"Unsupported geometry value type: {type(value).__name__}")


def _safely_repair(geom: BaseGeometry) -> BaseGeometry:
    if geom.is_valid and not geom.is_empty:
        return geom
    repaired = make_valid(geom)
    if repaired.is_valid and not repaired.is_empty:
        return repaired
    repaired = geom.buffer(0)
    return repaired


def _to_multipolygon(geom: BaseGeometry) -> MultiPolygon:
    if isinstance(geom, MultiPolygon):
        return geom
    if isinstance(geom, Polygon):
        return MultiPolygon([geom])
    raise ValueError(
        f"Geometry must be Polygon or MultiPolygon, got {geom.geom_type}"
    )


def _bounds_within_victoria(geom: BaseGeometry) -> bool:
    minx, miny, maxx, maxy = geom.bounds
    return (
        minx >= VIC_LON_MIN - _BOUNDS_TOLERANCE
        and maxx <= VIC_LON_MAX + _BOUNDS_TOLERANCE
        and miny >= VIC_LAT_MIN - _BOUNDS_TOLERANCE
        and maxy <= VIC_LAT_MAX + _BOUNDS_TOLERANCE
    )


def _first_present(record: dict[str, Any], keys: Iterable[str]) -> Any:
    for key in keys:
        if key in record and record[key] not in (None, ""):
            return record[key]
    return None


def _normalise_record(record: dict[str, Any], data_source_default: str) -> dict[str, Any]:
    out: dict[str, Any] = {}
    out["lga_code"] = _first_present(record, _LGA_CODE_ALIASES)
    out["lga_name"] = _first_present(record, _LGA_NAME_ALIASES)
    out["state"] = _first_present(record, _STATE_ALIASES) or "VIC"
    out["data_source"] = _first_present(record, _DATA_SOURCE_ALIASES) or data_source_default
    out["geometry"] = _first_present(record, _GEOMETRY_ALIASES)
    return out


def read_lga_boundaries_geojson(input_path: str | Path) -> list[dict[str, Any]]:
    """Read a GeoJSON FeatureCollection (or a list of Features)."""
    path = Path(input_path)
    if not path.is_file():
        raise FileNotFoundError(f"Boundary GeoJSON not found: {path}")
    with path.open(encoding="utf-8") as fh:
        payload = json.load(fh)

    features = payload.get("features") if isinstance(payload, dict) else payload
    if not isinstance(features, list):
        raise ValueError(f"GeoJSON does not contain a features array: {path}")

    out: list[dict[str, Any]] = []
    for feature in features:
        if not isinstance(feature, dict):
            continue
        properties = feature.get("properties") or {}
        geometry = feature.get("geometry")
        merged = {**properties, "geometry": geometry}
        normalised = _normalise_record(merged, data_source_default=path.stem)
        normalised["geometry"] = _coerce_to_geometry(normalised["geometry"])
        out.append(normalised)
    return out


def read_lga_boundaries_csv(input_path: str | Path) -> list[dict[str, Any]]:
    """Read a CSV with WKT geometry in a ``geometry``/``wkt`` column."""
    path = Path(input_path)
    if not path.is_file():
        raise FileNotFoundError(f"Boundary CSV not found: {path}")
    with path.open(encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        if reader.fieldnames is None:
            raise ValueError(f"CSV is empty or has no header: {path}")
        rows = list(reader)

    out: list[dict[str, Any]] = []
    for row in rows:
        normalised = _normalise_record(row, data_source_default=path.stem)
        normalised["geometry"] = _coerce_to_geometry(normalised["geometry"])
        out.append(normalised)
    return out


def _read_lga_boundaries_shapefile(input_path: str | Path) -> list[dict[str, Any]]:
    """Optional Shapefile reader; requires GeoPandas at runtime."""
    try:
        import geopandas as gpd
    except ImportError as exc:  # pragma: no cover - optional dep
        raise RuntimeError(
            "Shapefile ingestion requires GeoPandas. Install via `pip install geopandas`."
        ) from exc

    gdf = gpd.read_file(input_path)
    if gdf.crs is not None and str(gdf.crs).lower() != "epsg:4326":
        gdf = gdf.to_crs(epsg=4326)
    out: list[dict[str, Any]] = []
    for _, row in gdf.iterrows():
        record = {**row.drop("geometry").to_dict(), "geometry": row["geometry"]}
        normalised = _normalise_record(record, data_source_default=Path(input_path).stem)
        normalised["geometry"] = _coerce_to_geometry(normalised["geometry"])
        out.append(normalised)
    return out


def read_lga_boundaries_file(input_path: str | Path) -> list[dict[str, Any]]:
    """Dispatch by file extension to the appropriate reader."""
    path = Path(input_path)
    suffix = path.suffix.lower()
    if suffix in {".geojson", ".json"}:
        return read_lga_boundaries_geojson(path)
    if suffix == ".csv":
        return read_lga_boundaries_csv(path)
    if suffix == ".shp":
        return _read_lga_boundaries_shapefile(path)
    raise ValueError(
        f"Unsupported boundary file extension {suffix!r}; expected .geojson, .json, .csv, or .shp"
    )


def validate_lga_boundary_records(
    records: Iterable[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Validate metadata + geometry, repair invalid geometries safely."""
    seen_codes: set[str] = set()
    seen_name_state: set[tuple[str, str]] = set()
    out: list[dict[str, Any]] = []
    for record in records:
        # Normalise fields if a raw record was passed in directly
        normalised: dict[str, Any]
        if "lga_code" not in record or (record.get("geometry") is None and any(
            alt in record for alt in (*_GEOMETRY_ALIASES,) if alt != "geometry"
        )):
            normalised = _normalise_record(record, data_source_default="local_boundary_file")
            normalised["geometry"] = _coerce_to_geometry(normalised["geometry"])
        else:
            normalised = dict(record)

        meta = LgaBoundaryCsvRecord.model_validate(normalised)

        if meta.lga_code in seen_codes:
            raise ValueError(f"Duplicate lga_code in input: {meta.lga_code}")
        seen_codes.add(meta.lga_code)

        name_state_key = (meta.lga_name, meta.state)
        if name_state_key in seen_name_state:
            raise ValueError(
                f"Duplicate (lga_name, state) in input: {name_state_key}"
            )
        seen_name_state.add(name_state_key)

        geometry = normalised.get("geometry")
        if geometry is None:
            raise ValueError(f"Missing geometry for LGA {meta.lga_code}")
        if not isinstance(geometry, BaseGeometry):
            raise TypeError(
                f"Geometry for LGA {meta.lga_code} is not a Shapely object"
            )
        if geometry.is_empty:
            raise ValueError(f"Empty geometry for LGA {meta.lga_code}")

        repaired = _safely_repair(geometry)
        if not repaired.is_valid or repaired.is_empty:
            raise ValueError(
                f"Geometry for LGA {meta.lga_code} could not be safely repaired"
            )
        if not isinstance(repaired, (Polygon, MultiPolygon)):
            raise ValueError(
                f"Geometry for LGA {meta.lga_code} must be Polygon or MultiPolygon "
                f"(got {repaired.geom_type})"
            )
        if not _bounds_within_victoria(repaired):
            raise ValueError(
                f"Geometry for LGA {meta.lga_code} is outside Victoria-plausible bounds: "
                f"{repaired.bounds}"
            )

        out.append(
            {
                "lga_code": meta.lga_code,
                "lga_name": meta.lga_name,
                "state": meta.state,
                "data_source": meta.data_source,
                "geometry": repaired,
            }
        )
    return out


def project_lga_boundary_record_for_db(record: dict[str, Any]) -> dict[str, Any]:
    """Project a validated record to ``LgaBoundary`` ORM fields plus geom.

    Polygons are wrapped in a single-member MultiPolygon so the geometry
    matches the ``geometry(MULTIPOLYGON, 4326)`` column type.
    """
    meta = LgaBoundaryCreate.model_validate(record)
    geometry = record.get("geometry")
    if not isinstance(geometry, BaseGeometry):
        raise ValueError(
            f"project_lga_boundary_record_for_db: geometry missing for {meta.lga_code}"
        )
    multipoly = _to_multipolygon(geometry)
    geom = WKTElement(multipoly.wkt, srid=DEFAULT_SRID)
    return {
        "lga_code": meta.lga_code,
        "lga_name": meta.lga_name,
        "state": meta.state,
        "data_source": meta.data_source,
        "geom": geom,
    }


def _projected_to_orm(projected: dict[str, Any]) -> LgaBoundary:
    return LgaBoundary(**projected)


def load_lga_boundaries_to_db(
    records: Sequence[dict[str, Any]],
    db: Session,
    replace_existing: bool = False,
) -> int:
    """Insert LGA boundary rows; skipping or replacing duplicates by ``lga_code``."""
    if not records:
        return 0

    validated = validate_lga_boundary_records(records)
    incoming_codes = [r["lga_code"] for r in validated]

    try:
        if replace_existing:
            db.execute(
                delete(LgaBoundary).where(LgaBoundary.lga_code.in_(incoming_codes))
            )
            to_insert = validated
        else:
            existing_rows = db.execute(
                select(LgaBoundary.lga_code).where(
                    LgaBoundary.lga_code.in_(incoming_codes)
                )
            ).all()
            existing_codes = {row[0] for row in existing_rows}
            if existing_codes:
                logger.warning(
                    "Skipping %d existing lga_boundaries rows", len(existing_codes)
                )
            to_insert = [r for r in validated if r["lga_code"] not in existing_codes]

        orm_rows = [
            _projected_to_orm(project_lga_boundary_record_for_db(r)) for r in to_insert
        ]
        if orm_rows:
            db.add_all(orm_rows)
        db.commit()
        return len(orm_rows)
    except Exception:
        db.rollback()
        raise


def _geometry_to_geojson(geom: BaseGeometry) -> dict[str, Any]:
    return mapping(geom)


__all__ = [
    "DEFAULT_BOUNDARY_FILE",
    "load_lga_boundaries_to_db",
    "project_lga_boundary_record_for_db",
    "read_lga_boundaries_csv",
    "read_lga_boundaries_file",
    "read_lga_boundaries_geojson",
    "validate_lga_boundary_records",
]
