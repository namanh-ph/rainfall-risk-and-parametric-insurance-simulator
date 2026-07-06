"""CLI: assign assets to Victorian LGAs via PostGIS spatial join.

Usage examples:

    python -m src.cli.assign_lgas --replace-existing
    python -m src.cli.assign_lgas --no-nearest-fallback
    python -m src.cli.assign_lgas --max-fallback-distance-km 50
    python -m src.cli.assign_lgas --asset-ids VIC0001,VIC0002

This CLI operates on rows already loaded by ``ingest_data --assets``
and ``ingest_data --boundaries``.
"""

from __future__ import annotations

import argparse
import logging
import sys

from src.core.logging import configure_logging
from src.geospatial.lga_join import run_asset_lga_assignment


def _parse_max_distance(value: str | None) -> float | None:
    if value is None:
        return None
    if value.lower() in {"none", "null", ""}:
        return None
    return float(value)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="assign_lgas",
        description=(
            "Assign every asset (or an explicit subset) to a Victorian LGA "
            "using PostGIS spatial operations, persist the result on "
            "assets.lga_code, and print a run summary."
        ),
    )
    parser.add_argument(
        "--asset-id",
        action="append",
        default=[],
        metavar="ASSET_ID",
        help="Assign a single asset (repeatable). May be combined with --asset-ids.",
    )
    parser.add_argument(
        "--asset-ids",
        default=None,
        metavar="ASSET_ID,ASSET_ID,...",
        help="Comma-separated list of asset IDs to assign.",
    )
    parser.add_argument(
        "--allow-nearest-fallback",
        dest="allow_nearest_fallback",
        action="store_true",
        default=True,
        help="Enable nearest-LGA fallback for assets outside polygon coverage (default).",
    )
    parser.add_argument(
        "--no-nearest-fallback",
        dest="allow_nearest_fallback",
        action="store_false",
        help="Disable nearest-LGA fallback; leave gap-affected assets unmatched.",
    )
    parser.add_argument(
        "--max-fallback-distance-km",
        type=_parse_max_distance,
        default=25.0,
        help=(
            "Maximum nearest-fallback distance in kilometres (default 25). "
            "Pass 'none' to disable the cap."
        ),
    )
    parser.add_argument(
        "--replace-existing",
        dest="replace_existing",
        action="store_true",
        default=True,
        help="Clear and rewrite lga_code for the incoming asset IDs (default).",
    )
    parser.add_argument(
        "--no-replace-existing",
        dest="replace_existing",
        action="store_false",
        help="Skip assets that already have lga_code set instead of overwriting.",
    )
    return parser


def _resolve_asset_ids(args: argparse.Namespace) -> list[str] | None:
    ids: list[str] = list(args.asset_id)
    if args.asset_ids:
        ids.extend(part.strip() for part in args.asset_ids.split(",") if part.strip())
    return ids if ids else None


def main(argv: list[str] | None = None) -> int:
    configure_logging()
    logger = logging.getLogger("assign_lgas")
    args = build_parser().parse_args(argv)

    asset_ids = _resolve_asset_ids(args)

    from src.db.session import SessionLocal

    session = SessionLocal()
    try:
        try:
            summary = run_asset_lga_assignment(
                session,
                asset_ids=asset_ids,
                allow_nearest_fallback=args.allow_nearest_fallback,
                max_fallback_distance_km=args.max_fallback_distance_km,
                replace_existing=args.replace_existing,
            )
        except ValueError as exc:
            logger.error("LGA assignment prerequisite failed: %s", exc)
            return 2
        except Exception as exc:
            logger.error("LGA assignment failed: %s", exc)
            return 3
    finally:
        session.close()

    parts = [
        f"considered={summary['assets_considered']}",
        f"lgas={summary['lga_boundaries_available']}",
        f"updated={summary['assets_updated']}",
        f"covers={summary['covers_assignments']}",
        f"intersects={summary['intersects_assignments']}",
        f"fallback={summary['nearest_fallback_assignments']}",
        f"unmatched={summary['unmatched_assets']}",
    ]
    print(" ".join(parts))
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
