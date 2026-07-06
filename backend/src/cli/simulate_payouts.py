"""CLI: simulate parametric rainfall payouts.

Usage examples:

    python -m src.cli.simulate_payouts --replace-existing
    python -m src.cli.simulate_payouts --as-of-date 2025-12-31
    python -m src.cli.simulate_payouts --asset-ids VIC0001,VIC0002
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import date

from src.core.logging import configure_logging
from src.domain.constants import (
    DEFAULT_PAYOUT_COVERAGE_MULTIPLIER,
    DEFAULT_PAYOUT_SIMULATION_ID,
    DEFAULT_PAYOUT_SIMULATION_NAME,
)
from src.insurance.payout import DEFAULT_AS_OF_DATE, run_payout_simulation


def _parse_iso_date(value: str) -> date:
    return date.fromisoformat(value)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="simulate_payouts",
        description=(
            "Simulate parametric rainfall payouts from "
            "rainfall_features.rainfall_3d_mm and asset coverage. "
            "Risk scoring, threshold sensitivity analysis, ML training, "
            "business API, and frontend options are intentionally not "
            "exposed."
        ),
    )
    parser.add_argument(
        "--asset-id",
        action="append",
        default=[],
        metavar="ASSET_ID",
        help="Simulate a single asset (repeatable).",
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
        "--simulation-id",
        default=DEFAULT_PAYOUT_SIMULATION_ID,
        metavar="SIMULATION_ID",
        help=f"simulation_runs.simulation_id. Default: {DEFAULT_PAYOUT_SIMULATION_ID}.",
    )
    parser.add_argument(
        "--simulation-name",
        default=DEFAULT_PAYOUT_SIMULATION_NAME,
        metavar="SIMULATION_NAME",
        help=f"simulation_runs.simulation_name. Default: {DEFAULT_PAYOUT_SIMULATION_NAME!r}.",
    )
    parser.add_argument(
        "--coverage-multiplier",
        type=float,
        default=DEFAULT_PAYOUT_COVERAGE_MULTIPLIER,
        help=(
            "Multiplier applied to each asset's coverage_limit. "
            f"Default: {DEFAULT_PAYOUT_COVERAGE_MULTIPLIER}."
        ),
    )
    parser.add_argument(
        "--replace-existing",
        dest="replace_existing",
        action="store_true",
        default=True,
        help="Delete existing payout_results rows for the (simulation_id, "
        "asset_id) pairs before inserting (default).",
    )
    parser.add_argument(
        "--no-replace-existing",
        dest="replace_existing",
        action="store_false",
        help="Skip existing payout rows instead of replacing them.",
    )
    parser.add_argument(
        "--no-risk-band",
        dest="include_risk_band",
        action="store_false",
        default=True,
        help="Skip optional risk_band context lookup from asset_risk_scores.",
    )
    return parser


def _resolve_asset_ids(args: argparse.Namespace) -> list[str] | None:
    ids: list[str] = list(args.asset_id)
    if args.asset_ids:
        ids.extend(part.strip() for part in args.asset_ids.split(",") if part.strip())
    return ids if ids else None


def main(argv: list[str] | None = None) -> int:
    configure_logging()
    logger = logging.getLogger("simulate_payouts")
    args = build_parser().parse_args(argv)

    asset_ids = _resolve_asset_ids(args)

    from src.db.session import SessionLocal

    session = SessionLocal()
    try:
        try:
            summary = run_payout_simulation(
                session,
                asset_ids=asset_ids,
                as_of_date=args.as_of_date,
                simulation_id=args.simulation_id,
                simulation_name=args.simulation_name,
                coverage_multiplier=args.coverage_multiplier,
                replace_existing=args.replace_existing,
                include_risk_band=args.include_risk_band,
            )
        except ValueError as exc:
            logger.error("Payout-simulation prerequisite failed: %s", exc)
            return 2
        except Exception as exc:
            logger.error("Payout simulation failed: %s", exc)
            return 3
    finally:
        session.close()

    avg = summary["average_payout_rate"]
    parts = [
        f"simulation={summary['simulation_id']}",
        f"considered={summary['assets_considered']}",
        f"features={summary['feature_records_available']}",
        f"generated={summary['payout_records_generated']}",
        f"inserted={summary['payout_records_inserted']}",
        f"triggered={summary['triggered_assets']}",
        f"not_triggered={summary['not_triggered_assets']}",
        f"total_payout={summary['total_estimated_payout']}",
        f"avg_rate={avg if avg is not None else 'n/a'}",
    ]
    print(" ".join(parts))
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
