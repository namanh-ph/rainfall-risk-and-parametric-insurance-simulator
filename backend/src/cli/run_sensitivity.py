"""CLI: run threshold and/or coverage-multiplier sensitivity sweeps.

Usage examples:

    python -m src.cli.run_sensitivity --thresholds --replace-existing
    python -m src.cli.run_sensitivity --coverage-multipliers
    python -m src.cli.run_sensitivity --combined --as-of-date 2025-12-31
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import date
from typing import Any

from src.core.logging import configure_logging
from src.insurance.payout import DEFAULT_AS_OF_DATE
from src.insurance.simulation import (
    run_combined_sensitivity,
    run_coverage_multiplier_sensitivity,
    run_threshold_sensitivity,
)


def _parse_iso_date(value: str) -> date:
    return date.fromisoformat(value)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="run_sensitivity",
        description=(
            "Run reusable payout simulation scenarios: threshold sensitivity, "
            "coverage multiplier sensitivity, or both."
        ),
    )
    parser.add_argument(
        "--thresholds",
        action="store_true",
        help="Run the default threshold-sensitivity suite (baseline + 3 sweeps).",
    )
    parser.add_argument(
        "--coverage-multipliers",
        action="store_true",
        help="Run the default coverage-multiplier suite (0.75, 1.00, 1.25, 1.50).",
    )
    parser.add_argument(
        "--combined",
        action="store_true",
        help="Run both sensitivity suites.",
    )
    parser.add_argument(
        "--asset-id",
        action="append",
        default=[],
        metavar="ASSET_ID",
        help="Run sensitivity for a single asset (repeatable).",
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
        help="Delete + rewrite payouts and simulation_runs rows for each scenario.",
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


def _print_scenario_lines(scenarios: list[dict[str, Any]]) -> None:
    for sc in scenarios:
        summary = sc["summary"]
        print(
            f"scenario={sc['simulation_id']}"
            f" coverage_multiplier={sc['coverage_multiplier']}"
            f" generated={sc['payout_records_generated']}"
            f" inserted={sc['payout_records_inserted']}"
            f" triggered={summary['triggered_assets']}"
            f" total_payout={summary['total_estimated_payout']}"
            f" avg_rate={summary['average_payout_rate']}"
        )


def main(argv: list[str] | None = None) -> int:
    configure_logging()
    logger = logging.getLogger("run_sensitivity")
    args = build_parser().parse_args(argv)

    # Default to thresholds when no mode flag is provided
    if not (args.thresholds or args.coverage_multipliers or args.combined):
        args.thresholds = True

    asset_ids = _resolve_asset_ids(args)

    from src.db.session import SessionLocal

    session = SessionLocal()
    try:
        try:
            if args.combined:
                summary = run_combined_sensitivity(
                    session,
                    asset_ids=asset_ids,
                    as_of_date=args.as_of_date,
                    replace_existing=args.replace_existing,
                    include_risk_band=args.include_risk_band,
                )
                print("== Threshold sensitivity ==")
                _print_scenario_lines(summary["threshold_sensitivity"]["scenarios"])
                print("== Coverage-multiplier sensitivity ==")
                _print_scenario_lines(
                    summary["coverage_multiplier_sensitivity"]["scenarios"]
                )
            elif args.thresholds and args.coverage_multipliers:
                t = run_threshold_sensitivity(
                    session,
                    asset_ids=asset_ids,
                    as_of_date=args.as_of_date,
                    replace_existing=args.replace_existing,
                    include_risk_band=args.include_risk_band,
                )
                c = run_coverage_multiplier_sensitivity(
                    session,
                    asset_ids=asset_ids,
                    as_of_date=args.as_of_date,
                    replace_existing=args.replace_existing,
                    include_risk_band=args.include_risk_band,
                )
                print("== Threshold sensitivity ==")
                _print_scenario_lines(t["scenarios"])
                print("== Coverage-multiplier sensitivity ==")
                _print_scenario_lines(c["scenarios"])
            elif args.coverage_multipliers:
                c = run_coverage_multiplier_sensitivity(
                    session,
                    asset_ids=asset_ids,
                    as_of_date=args.as_of_date,
                    replace_existing=args.replace_existing,
                    include_risk_band=args.include_risk_band,
                )
                _print_scenario_lines(c["scenarios"])
            else:
                t = run_threshold_sensitivity(
                    session,
                    asset_ids=asset_ids,
                    as_of_date=args.as_of_date,
                    replace_existing=args.replace_existing,
                    include_risk_band=args.include_risk_band,
                )
                _print_scenario_lines(t["scenarios"])
        except ValueError as exc:
            logger.error("Sensitivity prerequisite failed: %s", exc)
            return 2
        except Exception as exc:
            logger.error("Sensitivity run failed: %s", exc)
            return 3
    finally:
        session.close()

    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
