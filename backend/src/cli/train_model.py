"""CLI: train the LightGBM risk-ranking model.

Usage examples:

    python -m src.cli.train_model
    python -m src.cli.train_model --no-mlflow
    python -m src.cli.train_model --feature-version rainfall_risk_features_v1 \\
        --model-name rainfall_risk_lgbm --model-version v1

"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import date
from pathlib import Path

from src.core.logging import configure_logging
from src.ml.tracking import DEFAULT_EXPERIMENT_NAME
from src.ml.training import (
    DEFAULT_AS_OF_DATE,
    DEFAULT_FEATURE_VERSION,
    DEFAULT_MODEL_NAME,
    DEFAULT_MODEL_VERSION,
    run_lightgbm_training,
)


def _parse_iso_date(value: str) -> date:
    return date.fromisoformat(value)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="train_model",
        description=(
            "Train the LightGBM rainfall-risk ranking model from "
            "model_training_data, evaluate it, save local artefacts, "
            "and (best-effort) log the run to MLflow."
        ),
    )
    parser.add_argument(
        "--asset-id",
        action="append",
        default=[],
        metavar="ASSET_ID",
        help="Train on a single asset (repeatable).",
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
        help=f"Model version tag. Default: {DEFAULT_MODEL_VERSION}.",
    )
    parser.add_argument(
        "--test-size", type=float, default=0.2, help="Test-set fraction (default 0.2)."
    )
    parser.add_argument(
        "--split-seed", type=int, default=42, help="Split seed (default 42)."
    )
    parser.add_argument(
        "--random-state",
        type=int,
        default=42,
        help="LightGBM random_state (default 42).",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Override the default artefact directory.",
    )
    parser.add_argument(
        "--experiment-name",
        default=DEFAULT_EXPERIMENT_NAME,
        help=f"MLflow experiment name. Default: {DEFAULT_EXPERIMENT_NAME}.",
    )
    parser.add_argument(
        "--log-to-mlflow",
        dest="log_to_mlflow",
        action="store_true",
        default=True,
        help="Attempt MLflow logging (default).",
    )
    parser.add_argument(
        "--no-mlflow",
        dest="log_to_mlflow",
        action="store_false",
        help="Skip MLflow logging.",
    )
    return parser


def _resolve_asset_ids(args: argparse.Namespace) -> list[str] | None:
    ids: list[str] = list(args.asset_id)
    if args.asset_ids:
        ids.extend(part.strip() for part in args.asset_ids.split(",") if part.strip())
    return ids if ids else None


def main(argv: list[str] | None = None) -> int:
    configure_logging()
    logger = logging.getLogger("train_model")
    args = build_parser().parse_args(argv)

    asset_ids = _resolve_asset_ids(args)

    from src.db.session import SessionLocal

    session = SessionLocal()
    try:
        try:
            summary = run_lightgbm_training(
                session,
                as_of_date=args.as_of_date,
                feature_version=args.feature_version,
                model_name=args.model_name,
                model_version=args.model_version,
                asset_ids=asset_ids,
                test_size=args.test_size,
                split_seed=args.split_seed,
                random_state=args.random_state,
                output_dir=args.output_dir,
                experiment_name=args.experiment_name,
                log_to_mlflow=args.log_to_mlflow,
            )
        except ValueError as exc:
            logger.error("Training prerequisite failed: %s", exc)
            return 2
        except Exception as exc:
            logger.error("Training failed: %s", exc)
            return 3
    finally:
        session.close()

    metrics = summary["metrics"]
    top = summary["top_features"][:3]
    parts = [
        f"model={summary['model_name']}/{summary['model_version']}",
        f"train={summary['train_row_count']}",
        f"test={summary['test_row_count']}",
        f"features={summary['feature_count']}",
        f"positive_rate={summary['positive_rate']}",
        f"roc_auc={metrics.get('roc_auc')}",
        f"pr_auc={metrics.get('pr_auc')}",
        f"precision@10pct={metrics.get('precision_at_top_10_pct')}",
        f"recall@10pct={metrics.get('recall_at_top_10_pct')}",
        f"lift@10pct={metrics.get('lift_at_top_10_pct')}",
        f"artifact_path={summary['artifact_path']}",
        f"mlflow_logged={summary['mlflow_logged']}",
    ]
    print(" ".join(parts))
    if top:
        print("top_features: " + ", ".join(f["feature"] for f in top))
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
