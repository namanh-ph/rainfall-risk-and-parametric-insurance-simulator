"""CLI: build the ML training dataset into ``model_training_data``.

Usage examples:

    python -m src.cli.build_training_data --replace-existing
    python -m src.cli.build_training_data --feature-version rainfall_risk_features_v1
    python -m src.cli.build_training_data --asset-ids VIC0001,VIC0002
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import date

from src.core.logging import configure_logging
from src.domain.constants import DEFAULT_PAYOUT_SIMULATION_ID
from src.ml.dataset import (
    DEFAULT_AS_OF_DATE,
    DEFAULT_FEATURE_VERSION,
    run_model_training_data_build,
)
from src.ml.splits import summarise_train_test_split


def _parse_iso_date(value: str) -> date:
    return date.fromisoformat(value)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="build_training_data",
        description=(
            "Build the ML training dataset by joining assets, rainfall features, "
            "risk scores, and payout context, then persist one row per "
            "(asset_id, as_of_date, feature_version) into model_training_data."
        ),
    )
    parser.add_argument(
        "--asset-id",
        action="append",
        default=[],
        metavar="ASSET_ID",
        help="Build training data for a single asset (repeatable).",
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
        "--feature-version",
        default=DEFAULT_FEATURE_VERSION,
        help=f"Feature-set version tag. Default: {DEFAULT_FEATURE_VERSION}.",
    )
    parser.add_argument(
        "--baseline-simulation-id",
        default=DEFAULT_PAYOUT_SIMULATION_ID,
        help=(
            "simulation_runs.simulation_id used to attach baseline payout context. "
            f"Default: {DEFAULT_PAYOUT_SIMULATION_ID}."
        ),
    )
    parser.add_argument(
        "--replace-existing",
        dest="replace_existing",
        action="store_true",
        default=True,
        help="Delete + rewrite model_training_data rows for the incoming "
        "(asset_id, as_of_date, feature_version) triplets (default).",
    )
    parser.add_argument(
        "--no-replace-existing",
        dest="replace_existing",
        action="store_false",
        help="Skip existing training rows instead of replacing them.",
    )
    parser.add_argument(
        "--test-size",
        type=float,
        default=0.2,
        help="Deterministic test-set fraction (default 0.2).",
    )
    parser.add_argument(
        "--split-seed",
        type=int,
        default=42,
        help="Seed for the deterministic train/test split (default 42).",
    )
    return parser


def _resolve_asset_ids(args: argparse.Namespace) -> list[str] | None:
    ids: list[str] = list(args.asset_id)
    if args.asset_ids:
        ids.extend(part.strip() for part in args.asset_ids.split(",") if part.strip())
    return ids if ids else None


def main(argv: list[str] | None = None) -> int:
    configure_logging()
    logger = logging.getLogger("build_training_data")
    args = build_parser().parse_args(argv)

    asset_ids = _resolve_asset_ids(args)

    from src.db.session import SessionLocal

    session = SessionLocal()
    try:
        try:
            summary = run_model_training_data_build(
                session,
                asset_ids=asset_ids,
                as_of_date=args.as_of_date,
                feature_version=args.feature_version,
                baseline_simulation_id=args.baseline_simulation_id,
                replace_existing=args.replace_existing,
            )
        except ValueError as exc:
            logger.error("Training-data build prerequisite failed: %s", exc)
            return 2
        except Exception as exc:
            logger.error("Training-data build failed: %s", exc)
            return 3

        # Compute the deterministic train/test split summary from the records
        # we just generated (subset = asset_ids if provided, else everything)
        from src.ml.dataset import fetch_model_training_inputs

        rows = fetch_model_training_inputs(
            session,
            asset_ids=asset_ids,
            as_of_date=args.as_of_date,
            baseline_simulation_id=args.baseline_simulation_id,
        )
    finally:
        session.close()

    split_summary = summarise_train_test_split(
        rows, test_size=args.test_size, seed=args.split_seed
    )

    parts = [
        f"feature_version={summary['feature_version']}",
        f"considered={summary['assets_considered']}",
        f"generated={summary['records_generated']}",
        f"inserted={summary['records_inserted']}",
        f"positive={summary['positive_targets']}",
        f"negative={summary['negative_targets']}",
        f"positive_rate={summary['positive_target_rate']}",
        f"train={split_summary['train_count']}",
        f"test={split_summary['test_count']}",
        f"test_rate={split_summary['test_rate']}",
    ]
    print(" ".join(parts))
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
