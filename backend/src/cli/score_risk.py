"""CLI: compute rule-based rainfall risk scores for assets with features.

Usage examples:

    python -m src.cli.score_risk --replace-existing
    python -m src.cli.score_risk --as-of-date 2025-12-31
    python -m src.cli.score_risk --asset-ids VIC0001,VIC0002
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import date

from src.core.logging import configure_logging
from src.risk.scoring import DEFAULT_AS_OF_DATE, run_asset_risk_scoring


def _parse_iso_date(value: str) -> date:
    return date.fromisoformat(value)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="score_risk",
        description=(
            "Compute interpretable rule-based rainfall risk scores from "
            "rainfall_features, asset exposure, vulnerability assumptions, "
            "and station confidence."
        ),
    )
    parser.add_argument(
        "--asset-id",
        action="append",
        default=[],
        metavar="ASSET_ID",
        help="Score a single asset (repeatable).",
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
        help="Delete existing asset_risk_scores rows for the (asset_id, "
        "as_of_date) pairs before inserting (default).",
    )
    parser.add_argument(
        "--no-replace-existing",
        dest="replace_existing",
        action="store_false",
        help="Skip existing risk-score rows instead of replacing them.",
    )
    return parser


def _resolve_asset_ids(args: argparse.Namespace) -> list[str] | None:
    ids: list[str] = list(args.asset_id)
    if args.asset_ids:
        ids.extend(part.strip() for part in args.asset_ids.split(",") if part.strip())
    return ids if ids else None


def main(argv: list[str] | None = None) -> int:
    configure_logging()
    logger = logging.getLogger("score_risk")
    args = build_parser().parse_args(argv)

    asset_ids = _resolve_asset_ids(args)

    from src.db.session import SessionLocal

    session = SessionLocal()
    try:
        try:
            summary = run_asset_risk_scoring(
                session,
                asset_ids=asset_ids,
                as_of_date=args.as_of_date,
                replace_existing=args.replace_existing,
            )
        except ValueError as exc:
            logger.error("Risk-scoring prerequisite failed: %s", exc)
            return 2
        except Exception as exc:
            logger.error("Risk scoring failed: %s", exc)
            return 3
    finally:
        session.close()

    avg = summary["average_risk_score"]
    parts = [
        f"considered={summary['assets_considered']}",
        f"features={summary['feature_records_available']}",
        f"generated={summary['risk_score_records_generated']}",
        f"inserted={summary['risk_score_records_inserted']}",
        f"low={summary['low_risk_assets']}",
        f"medium={summary['medium_risk_assets']}",
        f"high={summary['high_risk_assets']}",
        f"severe={summary['severe_risk_assets']}",
        f"avg={avg if avg is not None else 'n/a'}",
    ]
    print(" ".join(parts))
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
