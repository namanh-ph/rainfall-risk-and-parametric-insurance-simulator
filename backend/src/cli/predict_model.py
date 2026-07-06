"""CLI: load a trained LightGBM artefact and persist batch predictions.

Usage examples:

    python -m src.cli.predict_model --replace-existing
    python -m src.cli.predict_model --model-version v2
    python -m src.cli.predict_model --asset-ids VIC0001,VIC0002
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import date
from pathlib import Path

from src.core.logging import configure_logging
from src.ml.dataset import DEFAULT_FEATURE_VERSION
from src.ml.prediction import (
    DEFAULT_AS_OF_DATE,
    DEFAULT_MODEL_NAME,
    DEFAULT_MODEL_VERSION,
    run_batch_prediction,
)


def _parse_iso_date(value: str) -> date:
    return date.fromisoformat(value)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="predict_model",
        description=(
            "Generate batch predictions from a trained LightGBM artefact "
            "and persist them into the model_predictions table."
        ),
    )
    parser.add_argument(
        "--asset-id",
        action="append",
        default=[],
        metavar="ASSET_ID",
        help="Predict for a single asset (repeatable).",
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
        "--model-name",
        default=DEFAULT_MODEL_NAME,
        help=f"Model name. Default: {DEFAULT_MODEL_NAME}.",
    )
    parser.add_argument(
        "--model-version",
        default=DEFAULT_MODEL_VERSION,
        help=f"Model version. Default: {DEFAULT_MODEL_VERSION}.",
    )
    parser.add_argument(
        "--artifact-dir",
        type=Path,
        default=None,
        metavar="DIR",
        help=(
            "Model artefact directory. Defaults to "
            "backend/artifacts/models/<model_name>_<model_version>_<as_of_date>."
        ),
    )
    parser.add_argument(
        "--replace-existing",
        dest="replace_existing",
        action="store_true",
        default=True,
        help="Delete + rewrite model_predictions rows for the "
        "(asset_id, as_of_date, model_name, model_version) quadruplet (default).",
    )
    parser.add_argument(
        "--no-replace-existing",
        dest="replace_existing",
        action="store_false",
        help="Skip existing prediction rows instead of replacing them.",
    )
    return parser


def _resolve_asset_ids(args: argparse.Namespace) -> list[str] | None:
    ids: list[str] = list(args.asset_id)
    if args.asset_ids:
        ids.extend(part.strip() for part in args.asset_ids.split(",") if part.strip())
    return ids if ids else None


def main(argv: list[str] | None = None) -> int:
    configure_logging()
    logger = logging.getLogger("predict_model")
    args = build_parser().parse_args(argv)

    asset_ids = _resolve_asset_ids(args)

    from src.db.session import SessionLocal

    session = SessionLocal()
    try:
        try:
            summary = run_batch_prediction(
                session,
                artifact_dir=args.artifact_dir,
                as_of_date=args.as_of_date,
                feature_version=args.feature_version,
                model_name=args.model_name,
                model_version=args.model_version,
                asset_ids=asset_ids,
                replace_existing=args.replace_existing,
            )
        except (ValueError, FileNotFoundError) as exc:
            logger.error("Prediction prerequisite failed: %s", exc)
            return 2
        except Exception as exc:
            logger.error("Prediction failed: %s", exc)
            return 3
    finally:
        session.close()

    top_drivers = summary["top_risk_driver_counts"]
    top_drivers_top3 = sorted(
        top_drivers.items(), key=lambda kv: -kv[1]
    )[:3]

    parts = [
        f"model={summary['model_name']}/{summary['model_version']}",
        f"records={summary['records_loaded']}",
        f"generated={summary['prediction_records_generated']}",
        f"inserted={summary['prediction_records_inserted']}",
        f"min={summary['min_probability']}",
        f"median={summary['median_probability']}",
        f"max={summary['max_probability']}",
        f"top={summary['top_ranked_asset_id']}",
        f"drivers={top_drivers_top3}",
        f"warnings={len(summary['warnings'])}",
    ]
    print(" ".join(parts))
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
