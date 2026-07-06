"""CLI: generate rainfall features for matched assets.

Usage examples:

    python -m src.cli.generate_features --rainfall --replace-existing
    python -m src.cli.generate_features --rainfall --as-of-date 2025-12-31
    python -m src.cli.generate_features --rainfall --asset-ids VIC0001,VIC0002
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import date

from src.core.logging import configure_logging
from src.features.rainfall_features import (
    DEFAULT_AS_OF_DATE,
    run_rainfall_feature_generation,
)


def _parse_iso_date(value: str) -> date:
    return date.fromisoformat(value)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="generate_features",
        description=(
            "Engineer asset-level rainfall features (trailing totals, "
            "station percentiles, extreme flag) from rainfall_observations "
            "and asset_station_mapping."
        ),
    )
    parser.add_argument(
        "--rainfall",
        action="store_true",
        help="Run rainfall feature generation (currently the only feature family).",
    )
    parser.add_argument(
        "--asset-id",
        action="append",
        default=[],
        metavar="ASSET_ID",
        help="Generate features for a single asset (repeatable).",
    )
    parser.add_argument(
        "--asset-ids",
        default=None,
        metavar="ASSET_ID,ASSET_ID,...",
        help="Comma-separated list of asset IDs.",
    )
    parser.add_argument(
        "--as-of-date",
        type=_parse_iso_date,
        default=DEFAULT_AS_OF_DATE,
        help=f"As-of date (YYYY-MM-DD). Default: {DEFAULT_AS_OF_DATE.isoformat()}.",
    )
    parser.add_argument(
        "--replace-existing",
        dest="replace_existing",
        action="store_true",
        default=True,
        help="Delete existing rainfall_features rows for the (asset_id, as_of_date) "
        "pairs before inserting (default).",
    )
    parser.add_argument(
        "--no-replace-existing",
        dest="replace_existing",
        action="store_false",
        help="Skip existing feature rows instead of replacing them.",
    )
    return parser


def _resolve_asset_ids(args: argparse.Namespace) -> list[str] | None:
    ids: list[str] = list(args.asset_id)
    if args.asset_ids:
        ids.extend(part.strip() for part in args.asset_ids.split(",") if part.strip())
    return ids if ids else None


def main(argv: list[str] | None = None) -> int:
    configure_logging()
    logger = logging.getLogger("generate_features")
    args = build_parser().parse_args(argv)

    if not args.rainfall:
        logger.error(
            "Specify --rainfall (currently the only supported feature family)."
        )
        return 2

    asset_ids = _resolve_asset_ids(args)

    from src.db.session import SessionLocal

    session = SessionLocal()
    try:
        try:
            summary = run_rainfall_feature_generation(
                session,
                asset_ids=asset_ids,
                as_of_date=args.as_of_date,
                replace_existing=args.replace_existing,
            )
        except ValueError as exc:
            logger.error("Feature generation prerequisite failed: %s", exc)
            return 2
        except Exception as exc:
            logger.error("Feature generation failed: %s", exc)
            return 3
    finally:
        session.close()

    parts = [
        f"considered={summary['assets_considered']}",
        f"mapped={summary['mapped_assets']}",
        f"stations={summary['stations_used']}",
        f"generated={summary['feature_records_generated']}",
        f"inserted={summary['feature_records_inserted']}",
        f"no_obs={summary['assets_without_observations']}",
        f"extreme={summary['extreme_rainfall_assets']}",
    ]
    print(" ".join(parts))
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
