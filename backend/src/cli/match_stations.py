"""CLI: run asset-to-station nearest-neighbour matching.

Usage examples:

    python -m src.cli.match_stations --replace-existing
    python -m src.cli.match_stations --asset-id VIC0001 --asset-id VIC0002
    python -m src.cli.match_stations --asset-ids VIC0001,VIC0002,VIC0003
    python -m src.cli.match_stations --max-distance-km 75 --no-replace-existing

This CLI operates on rows already loaded by ``ingest_data --assets``.
"""

from __future__ import annotations

import argparse
import logging
import sys

from src.core.logging import configure_logging
from src.geospatial.station_matching import run_asset_station_matching


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="match_stations",
        description=(
            "Match every asset (or an explicit subset) to its nearest rainfall "
            "station, persist the mapping into asset_station_mapping, and print "
            "a run summary."
        ),
    )
    parser.add_argument(
        "--asset-id",
        action="append",
        default=[],
        metavar="ASSET_ID",
        help="Match a single asset (repeatable). May be combined with --asset-ids.",
    )
    parser.add_argument(
        "--asset-ids",
        default=None,
        metavar="ASSET_ID,ASSET_ID,...",
        help="Comma-separated list of asset IDs to match.",
    )
    parser.add_argument(
        "--max-distance-km",
        type=float,
        default=None,
        help=(
            "Optional upper bound (kilometres). Assets whose nearest station "
            "exceeds this distance are left unmatched."
        ),
    )
    parser.add_argument(
        "--replace-existing",
        dest="replace_existing",
        action="store_true",
        default=True,
        help="Replace existing mappings for the incoming asset IDs (default).",
    )
    parser.add_argument(
        "--no-replace-existing",
        dest="replace_existing",
        action="store_false",
        help="Skip existing mappings instead of replacing them.",
    )
    return parser


def _resolve_asset_ids(args: argparse.Namespace) -> list[str] | None:
    ids: list[str] = list(args.asset_id)
    if args.asset_ids:
        ids.extend(part.strip() for part in args.asset_ids.split(",") if part.strip())
    return ids if ids else None


def main(argv: list[str] | None = None) -> int:
    configure_logging()
    logger = logging.getLogger("match_stations")
    args = build_parser().parse_args(argv)

    asset_ids = _resolve_asset_ids(args)

    from src.db.session import SessionLocal

    session = SessionLocal()
    try:
        try:
            summary = run_asset_station_matching(
                session,
                asset_ids=asset_ids,
                max_distance_km=args.max_distance_km,
                replace_existing=args.replace_existing,
            )
        except ValueError as exc:
            logger.error("Matching prerequisite failed: %s", exc)
            return 2
        except Exception as exc:
            logger.error("Matching failed: %s", exc)
            return 3
    finally:
        session.close()

    parts = [
        f"considered={summary['assets_considered']}",
        f"stations={summary['stations_available']}",
        f"matched={summary['matches_generated']}",
        f"inserted={summary['mappings_inserted']}",
        f"unmatched={summary['unmatched_assets']}",
    ]
    print(" ".join(parts))
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
