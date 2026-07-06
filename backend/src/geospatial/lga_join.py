"""Asset-to-LGA spatial join.

Each asset is assigned to one Victorian LGA using PostGIS spatial
operations, with the priority order:

1. ``ST_Covers(lga.geom, asset.geom)``; exact polygon coverage
   (boundary-inclusive, preferred over ``ST_Contains``).
2. ``ST_Intersects(lga.geom, asset.geom)``; boundary-edge fallback for
   shared edges between adjacent polygons.
3. Optional nearest-LGA fallback via ``ST_Distance(geography(...))``;
   useful for assets near simplified-rectangle boundary gaps.

Persistence updates the existing nullable ``assets.lga_code`` foreign key
column. ``asset_station_mapping`` is intentionally untouched
"""

from __future__ import annotations

import logging
from collections import Counter
from collections.abc import Iterable, Sequence
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import bindparam, func, select, text, update
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import TextClause

from src.db.models import Asset, LgaBoundary
from src.schemas.lga_join import AssetLgaAssignmentRecord, AssetLgaAssignmentRunSummary

logger = logging.getLogger(__name__)


def build_asset_lga_join_query(
    asset_ids: Sequence[str] | None = None,
    allow_nearest_fallback: bool = True,
    max_fallback_distance_km: float | None = 25.0,
) -> tuple[TextClause, dict[str, Any]]:
    """Build the parameterised PostGIS asset→LGA query.

    Returns ``(text_clause, params)``. Asset IDs flow through an expanding
    bind parameter; ``max_fallback_distance_km`` flows through a scalar
    bind parameter. Raw user-supplied IDs are never interpolated into the
    SQL text
    """
    if max_fallback_distance_km is not None and max_fallback_distance_km <= 0:
        raise ValueError(
            f"max_fallback_distance_km must be positive when provided "
            f"(got {max_fallback_distance_km})"
        )

    params: dict[str, Any] = {}

    asset_filter = ""
    if asset_ids is not None:
        asset_filter = "WHERE a.asset_id IN :asset_ids"
        params["asset_ids"] = list(asset_ids)

    fallback_distance_filter = ""
    if allow_nearest_fallback and max_fallback_distance_km is not None:
        fallback_distance_filter = (
            "AND (ST_Distance(geography(c.geom), geography(l.geom)) / 1000.0) "
            "<= :max_fallback_distance_km"
        )
        params["max_fallback_distance_km"] = float(max_fallback_distance_km)

    if allow_nearest_fallback:
        fallback_cte_block = f""",
fallback_candidates AS (
    SELECT
        c.asset_id,
        l.lga_code,
        l.lga_name,
        'nearest_fallback' AS assignment_method,
        ST_Distance(geography(c.geom), geography(l.geom)) / 1000.0 AS assignment_distance_km
    FROM considered c
    CROSS JOIN LATERAL (
        SELECT lga_code, lga_name, geom
        FROM lga_boundaries
        ORDER BY geography(c.geom) <-> geography(geom)
        LIMIT 1
    ) l
    WHERE NOT EXISTS (
        SELECT 1 FROM polygon_candidates pc WHERE pc.asset_id = c.asset_id
    )
    {fallback_distance_filter}
)"""
        fallback_union = "UNION ALL SELECT * FROM fallback_candidates"
    else:
        fallback_cte_block = ""
        fallback_union = ""

    sql = f"""
WITH considered AS (
    SELECT a.asset_id, a.geom
    FROM assets a
    {asset_filter}
),
polygon_candidates AS (
    SELECT
        c.asset_id,
        l.lga_code,
        l.lga_name,
        CASE WHEN ST_Covers(l.geom, c.geom) THEN 'covers' ELSE 'intersects' END AS assignment_method,
        0.0 AS assignment_distance_km
    FROM considered c
    JOIN lga_boundaries l ON ST_Intersects(l.geom, c.geom)
){fallback_cte_block},
all_candidates AS (
    SELECT * FROM polygon_candidates
    {fallback_union}
),
ranked AS (
    SELECT
        *,
        ROW_NUMBER() OVER (
            PARTITION BY asset_id
            ORDER BY
                CASE assignment_method
                    WHEN 'covers' THEN 1
                    WHEN 'intersects' THEN 2
                    WHEN 'nearest_fallback' THEN 3
                    ELSE 4
                END,
                assignment_distance_km ASC NULLS LAST,
                lga_code ASC
        ) AS rn
    FROM all_candidates
)
SELECT
    c.asset_id AS asset_id,
    r.lga_code AS lga_code,
    r.lga_name AS lga_name,
    COALESCE(r.assignment_method, 'unmatched') AS assignment_method,
    r.assignment_distance_km AS assignment_distance_km
FROM considered c
LEFT JOIN ranked r ON c.asset_id = r.asset_id AND r.rn = 1
""".strip()

    stmt = text(sql)
    if "asset_ids" in params:
        stmt = stmt.bindparams(bindparam("asset_ids", expanding=True))
    return stmt, params


def fetch_asset_lga_assignments(
    db: Session,
    asset_ids: Sequence[str] | None = None,
    allow_nearest_fallback: bool = True,
    max_fallback_distance_km: float | None = 25.0,
) -> list[dict[str, Any]]:
    """Run the LGA join query and stamp ``assigned_at`` on every row"""
    stmt, params = build_asset_lga_join_query(
        asset_ids,
        allow_nearest_fallback=allow_nearest_fallback,
        max_fallback_distance_km=max_fallback_distance_km,
    )
    result = db.execute(stmt, params)
    now = datetime.now(UTC)
    out: list[dict[str, Any]] = []
    for row in result:
        mapping = row._mapping
        method = str(mapping["assignment_method"])
        distance = mapping["assignment_distance_km"]
        if method in ("covers", "intersects"):
            distance_value: float | None = 0.0
        elif method == "unmatched":
            distance_value = None
        else:  # nearest_fallback
            distance_value = float(distance) if distance is not None else 0.0
        out.append(
            {
                "asset_id": str(mapping["asset_id"]),
                "lga_code": (
                    str(mapping["lga_code"]) if mapping["lga_code"] is not None else None
                ),
                "lga_name": (
                    str(mapping["lga_name"]) if mapping["lga_name"] is not None else None
                ),
                "assignment_method": method,
                "assignment_distance_km": distance_value,
                "assigned_at": now,
            }
        )
    return out


def validate_lga_assignments(
    assignments: Iterable[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Validate every assignment through ``AssetLgaAssignmentRecord`` + uniqueness"""
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for record in assignments:
        validated = AssetLgaAssignmentRecord.model_validate(record)
        if validated.asset_id in seen:
            raise ValueError(
                f"Duplicate asset_id in assignment batch: {validated.asset_id}"
            )
        seen.add(validated.asset_id)
        out.append(validated.model_dump())
    return out


def persist_asset_lga_assignments(
    assignments: Sequence[dict[str, Any]],
    db: Session,
    replace_existing: bool = True,
) -> int:
    """Update ``assets.lga_code`` from the assignment batch.

    Only assignments with method != 'unmatched' write a non-null lga_code.
    Returns the count of assets actually updated to a non-null lga_code
    """
    if not assignments:
        return 0

    validated = validate_lga_assignments(assignments)
    matched = [a for a in validated if a["assignment_method"] != "unmatched"]
    incoming_ids = [a["asset_id"] for a in validated]

    try:
        if replace_existing and incoming_ids:
            # Clear existing lga_code for every asset in the batch (matched or
            # unmatched). Unmatched assets thus end up NULL again, even if a
            # previous run had assigned them to an LGA
            db.execute(
                update(Asset)
                .where(Asset.asset_id.in_(incoming_ids))
                .values(lga_code=None)
            )
            to_apply = matched
        else:
            existing_rows = db.execute(
                select(Asset.asset_id, Asset.lga_code)
                .where(Asset.asset_id.in_([a["asset_id"] for a in matched]))
                .where(Asset.lga_code.isnot(None))
            ).all()
            already_set = {row[0] for row in existing_rows}
            if already_set:
                logger.warning(
                    "Skipping %d assets that already have lga_code set "
                    "(replace_existing=False)",
                    len(already_set),
                )
            to_apply = [a for a in matched if a["asset_id"] not in already_set]

        # Batch updates by lga_code so we issue ~len(distinct lga_codes) queries
        # rather than one per asset
        by_lga: dict[str, list[str]] = {}
        for assignment in to_apply:
            by_lga.setdefault(assignment["lga_code"], []).append(assignment["asset_id"])

        for lga_code, asset_ids in by_lga.items():
            db.execute(
                update(Asset)
                .where(Asset.asset_id.in_(asset_ids))
                .values(lga_code=lga_code)
            )

        db.commit()
        return len(to_apply)
    except Exception:
        db.rollback()
        raise


def run_asset_lga_assignment(
    db: Session,
    asset_ids: Sequence[str] | None = None,
    allow_nearest_fallback: bool = True,
    max_fallback_distance_km: float | None = 25.0,
    replace_existing: bool = True,
) -> dict[str, Any]:
    """Run the full assignment pipeline and return a structured summary"""
    n_assets = db.execute(select(func.count()).select_from(Asset)).scalar() or 0
    n_lgas = db.execute(select(func.count()).select_from(LgaBoundary)).scalar() or 0

    if n_assets == 0:
        raise ValueError("No assets in database; cannot run LGA assignment")
    if n_lgas == 0:
        raise ValueError("No lga_boundaries in database; cannot run LGA assignment")

    considered = len(asset_ids) if asset_ids is not None else int(n_assets)

    assignments = fetch_asset_lga_assignments(
        db,
        asset_ids=asset_ids,
        allow_nearest_fallback=allow_nearest_fallback,
        max_fallback_distance_km=max_fallback_distance_km,
    )
    updated = persist_asset_lga_assignments(assignments, db, replace_existing)

    methods = Counter(a["assignment_method"] for a in assignments)

    summary = {
        "assets_considered": considered,
        "lga_boundaries_available": int(n_lgas),
        "assignments_generated": len(assignments),
        "assets_updated": updated,
        "unmatched_assets": methods.get("unmatched", 0),
        "covers_assignments": methods.get("covers", 0),
        "intersects_assignments": methods.get("intersects", 0),
        "nearest_fallback_assignments": methods.get("nearest_fallback", 0),
        "allow_nearest_fallback": allow_nearest_fallback,
        "max_fallback_distance_km": max_fallback_distance_km,
        "replace_existing": replace_existing,
    }
    AssetLgaAssignmentRunSummary.model_validate(summary)
    return summary


__all__ = [
    "build_asset_lga_join_query",
    "fetch_asset_lga_assignments",
    "persist_asset_lga_assignments",
    "run_asset_lga_assignment",
    "validate_lga_assignments",
]
