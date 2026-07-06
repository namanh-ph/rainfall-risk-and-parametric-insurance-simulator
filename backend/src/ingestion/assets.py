"""Asset CSV loader.

This module reads the asset dataset committed at ``data/assets.csv``
and projects 9-field subset into the ``Asset`` ORM model.

downstream modules (LGA join,
nearest-station match, features, scoring, payouts) read from the persisted
``assets`` table — not from the CSV.
"""

from __future__ import annotations

import csv
import logging
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from geoalchemy2.elements import WKTElement
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from src.db.models import Asset
from src.domain.constants import DEFAULT_SRID
from src.schemas.assets import AssetDbCreate, StaticAssetCsvRecord

logger = logging.getLogger(__name__)

DEFAULT_ASSET_CSV = Path("../data/assets.csv")

REQUIRED_CSV_COLUMNS: tuple[str, ...] = (
    "asset_id",
    "business_type",
    "industry",
    "postcode",
    "latitude",
    "longitude",
    "asset_value",
    "annual_revenue",
    "coverage_limit",
)


def read_static_assets_csv(input_path: str | Path) -> list[dict[str, Any]]:
    """Read the asset CSV. Returns the rows as dicts.

    The CSV has 44 columns; this function preserves them all (the wider
    modelling/policy fields) so analytics consumers can still use the
    return value directly. DB persistence is handled by
    ``project_asset_record_for_db``.
    """
    path = Path(input_path)
    if not path.is_file():
        raise FileNotFoundError(f"Static asset CSV not found: {path}")
    with path.open(encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        if reader.fieldnames is None:
            raise ValueError(f"CSV is empty or has no header: {path}")
        missing = [c for c in REQUIRED_CSV_COLUMNS if c not in reader.fieldnames]
        if missing:
            raise ValueError(f"CSV missing required columns: {missing}")
        return list(reader)


def validate_static_asset_records(records: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Validate every CSV row through ``StaticAssetCsvRecord``.

    Enforces uniqueness of ``asset_id`` across the input batch. Returns
    each record as a Pydantic-normalised dict (extras preserved via
    ``extra='allow'``).
    """
    seen_ids: set[str] = set()
    out: list[dict[str, Any]] = []
    for record in records:
        validated = StaticAssetCsvRecord.model_validate(record)
        if validated.asset_id in seen_ids:
            raise ValueError(f"Duplicate asset_id in input: {validated.asset_id}")
        seen_ids.add(validated.asset_id)
        out.append(validated.model_dump())
    return out


def project_asset_record_for_db(record: dict[str, Any]) -> dict[str, Any]:
    """Project a CSV row to the 9 Asset ORM fields plus geom.

    lga_code is left None here; it is filled by the asset-to-LGA join in
    ``src.geospatial.lga_join``. Geometry is built as POINT(lon lat) at
    SRID 4326.
    """
    insert = AssetDbCreate.model_validate(record)
    geom = WKTElement(f"POINT({insert.longitude} {insert.latitude})", srid=DEFAULT_SRID)
    return {
        "asset_id": insert.asset_id,
        "business_type": insert.business_type,
        "industry": insert.industry,
        "postcode": insert.postcode,
        "latitude": insert.latitude,
        "longitude": insert.longitude,
        "asset_value": insert.asset_value,
        "annual_revenue": insert.annual_revenue,
        "coverage_limit": insert.coverage_limit,
        "geom": geom,
    }


def _projected_to_orm(projected: dict[str, Any]) -> Asset:
    return Asset(**projected)


def load_static_assets_to_db(
    input_path: str | Path,
    db: Session,
    replace_existing: bool = False,
) -> int:
    """Read, validate, project, and insert the static asset CSV.

    Returns the number of rows inserted. Existing IDs are skipped when
    ``replace_existing`` is False; deleted-and-replaced for the affected
    IDs when True. Commits once on success, rolls back on any failure.
    """
    raw_records = read_static_assets_csv(input_path)
    validated = validate_static_asset_records(raw_records)
    incoming_ids = [r["asset_id"] for r in validated]
    if not incoming_ids:
        return 0

    try:
        if replace_existing:
            db.execute(delete(Asset).where(Asset.asset_id.in_(incoming_ids)))
            to_insert = validated
        else:
            existing_rows = db.execute(
                select(Asset.asset_id).where(Asset.asset_id.in_(incoming_ids))
            ).all()
            existing_ids = {row[0] for row in existing_rows}
            if existing_ids:
                logger.warning(
                    "Skipping %d existing asset_id rows (replace_existing=False)",
                    len(existing_ids),
                )
            to_insert = [r for r in validated if r["asset_id"] not in existing_ids]

        orm_rows = [_projected_to_orm(project_asset_record_for_db(r)) for r in to_insert]
        if orm_rows:
            db.add_all(orm_rows)
        db.commit()
        return len(orm_rows)
    except Exception:
        db.rollback()
        raise


__all__ = [
    "DEFAULT_ASSET_CSV",
    "REQUIRED_CSV_COLUMNS",
    "load_static_assets_to_db",
    "project_asset_record_for_db",
    "read_static_assets_csv",
    "validate_static_asset_records",
]
