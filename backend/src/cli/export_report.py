"""CLI: export an HTML portfolio report from persisted analytics outputs.

Usage examples:

    python -m src.cli.export_report
    python -m src.cli.export_report --as-of-date 2025-12-31 --top-n 25
    python -m src.cli.export_report --no-methodology --no-top-assets
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import date

from pydantic import ValidationError

from src.core.logging import configure_logging
from src.domain.constants import DEFAULT_PAYOUT_SIMULATION_ID
from src.reports.export import export_portfolio_report
from src.schemas.api_reports import (
    DEFAULT_FEATURE_VERSION,
    DEFAULT_MODEL_NAME,
    DEFAULT_MODEL_VERSION,
    DEFAULT_REPORT_TITLE,
    ReportExportRequest,
)

DEFAULT_AS_OF_DATE = date(2025, 12, 31)


def _parse_iso_date(value: str) -> date:
    return date.fromisoformat(value)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="export_report",
        description=(
            "Generate an HTML portfolio risk report from persisted "
            "database outputs and write it under "
            "backend/artifacts/reports/."
        ),
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
        help=f"Simulation identifier. Default: {DEFAULT_PAYOUT_SIMULATION_ID}.",
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
        "--feature-version",
        default=DEFAULT_FEATURE_VERSION,
        help=f"Feature-set version tag. Default: {DEFAULT_FEATURE_VERSION}.",
    )
    parser.add_argument(
        "--report-title",
        default=DEFAULT_REPORT_TITLE,
        help=f"Report title. Default: {DEFAULT_REPORT_TITLE!r}.",
    )
    parser.add_argument(
        "--output",
        dest="output_filename",
        default=None,
        help=(
            "Optional output filename (must end with .html and contain "
            "no path separators). Defaults to a deterministic filename."
        ),
    )
    parser.add_argument(
        "--top-n",
        type=int,
        default=20,
        help="Number of top assets to include in top-risk / top-payout sections (1-100).",
    )
    parser.add_argument(
        "--no-methodology",
        dest="include_methodology",
        action="store_false",
        default=True,
        help="Omit the methodology section from the rendered report.",
    )
    parser.add_argument(
        "--no-top-assets",
        dest="include_top_assets",
        action="store_false",
        default=True,
        help="Omit the top-risk-assets and top-payout-assets sections.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    configure_logging()
    logger = logging.getLogger("export_report")
    args = build_parser().parse_args(argv)

    try:
        request = ReportExportRequest(
            as_of_date=args.as_of_date,
            simulation_id=args.simulation_id,
            model_name=args.model_name,
            model_version=args.model_version,
            feature_version=args.feature_version,
            report_title=args.report_title,
            output_filename=args.output_filename,
            include_methodology=args.include_methodology,
            include_top_assets=args.include_top_assets,
            top_n=args.top_n,
        )
    except ValidationError as exc:
        logger.error("Invalid arguments: %s", exc)
        return 2

    from src.db.session import SessionLocal

    session = SessionLocal()
    try:
        try:
            result = export_portfolio_report(session, request)
        except (ValueError, FileNotFoundError) as exc:
            logger.error("Report export prerequisite failed: %s", exc)
            return 2
        except OSError as exc:
            logger.error("Report export file writing failed: %s", exc)
            return 3
        except Exception as exc:
            logger.error("Report export failed: %s", exc)
            return 3
    finally:
        session.close()

    parts = [
        f"report_id={result['report_id']}",
        f"output={result['output_path']}",
        f"relative={result['relative_output_path']}",
        f"size_bytes={result['file_size_bytes']}",
        f"sections={len(result.get('sections', []))}",
        f"warnings={len(result.get('warnings') or [])}",
    ]
    print(" ".join(parts))
    for section in result.get("sections", []):
        print(
            f"  - {section['section']}: available={section['available']} "
            f"row_count={section['row_count']}"
        )
    for w in result.get("warnings") or []:
        print(f"  warning: {w}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
