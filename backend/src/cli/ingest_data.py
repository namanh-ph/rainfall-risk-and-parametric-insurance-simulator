"""CLI: ingest assets, rainfall stations, observations, and LGA boundaries.

Usage examples:

    python -m src.cli.ingest_data --assets
    python -m src.cli.ingest_data --rainfall
    python -m src.cli.ingest_data --assets --rainfall --boundaries --replace-existing

Every input is read from the CSV / GeoJSON files under ``data/``. The
ingestion layer is read-only: it never generates rows.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.orm import Session

from src.core.logging import configure_logging
from src.ingestion.assets import (
    DEFAULT_ASSET_CSV,
    load_static_assets_to_db,
)
from src.ingestion.boundaries import (
    DEFAULT_BOUNDARY_FILE,
    load_lga_boundaries_to_db,
    read_lga_boundaries_file,
)
from src.ingestion.rainfall import (
    DEFAULT_OBSERVATION_CSV,
    DEFAULT_STATION_CSV,
    load_rainfall_observations_to_db,
    load_rainfall_stations_to_db,
    read_rainfall_observations_csv,
    read_rainfall_stations_csv,
)


def _clear_for_full_ingest(
    db: Session,
    *,
    refresh_assets: bool,
    refresh_rainfall: bool,
    refresh_boundaries: bool,
    logger: logging.Logger,
) -> None:
    """TRUNCATE the requested parent tables + cascade-clear dependents.

    When ``--replace-existing`` is set, the new CSVs are treated as the
    source of truth, so rows missing from them must be removed and every
    derived/downstream table rebuilt from scratch by the pipeline. This
    sidesteps the FK violations that ID-scoped upserts run into when the
    incoming row set shrinks
    """
    targets: list[str] = []
    if refresh_assets:
        targets.append("assets")
    if refresh_rainfall:
        # rainfall_observations cascades from rainfall_stations, but list
        # it explicitly so observation-only refreshes also work
        targets.extend(("rainfall_observations", "rainfall_stations"))
    if refresh_boundaries:
        targets.append("lga_boundaries")
    if not targets:
        return

    statement = f"TRUNCATE {', '.join(targets)} RESTART IDENTITY CASCADE"
    logger.info(
        "Replace-existing pre-clear: %s (cascades through derived tables)",
        statement,
    )
    db.execute(text(statement))
    db.commit()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ingest_data",
        description=(
            "Ingest the asset CSV, rainfall data (stations + daily "
            "observations), and Victorian LGA boundaries into the "
            "simulator PostGIS database."
        ),
    )
    parser.add_argument(
        "--assets",
        action="store_true",
        help="Load the asset CSV into the assets table.",
    )
    parser.add_argument(
        "--rainfall",
        action="store_true",
        help="Load rainfall stations and observations.",
    )
    parser.add_argument(
        "--boundaries",
        action="store_true",
        help="Load Victorian LGA boundaries into the lga_boundaries table.",
    )
    parser.add_argument(
        "--asset-csv",
        type=Path,
        default=DEFAULT_ASSET_CSV,
        help=f"Path to the asset CSV (default: {DEFAULT_ASSET_CSV}).",
    )
    parser.add_argument(
        "--station-csv",
        type=Path,
        default=DEFAULT_STATION_CSV,
        help=f"Path to a rainfall station CSV (default: {DEFAULT_STATION_CSV}).",
    )
    parser.add_argument(
        "--observation-csv",
        type=Path,
        default=DEFAULT_OBSERVATION_CSV,
        help=f"Path to a rainfall observation CSV (default: {DEFAULT_OBSERVATION_CSV}).",
    )
    parser.add_argument(
        "--boundary-file",
        type=Path,
        default=DEFAULT_BOUNDARY_FILE,
        help=(
            "Path to an LGA boundary file (.geojson, .json, .csv with WKT, "
            f"or .shp). Default: {DEFAULT_BOUNDARY_FILE}."
        ),
    )
    parser.add_argument(
        "--replace-existing",
        action="store_true",
        help="Delete existing rows for the incoming IDs/keys before insert.",
    )
    return parser


def _ingest_assets(args: argparse.Namespace, logger: logging.Logger) -> int:
    from src.db.session import SessionLocal

    session = SessionLocal()
    try:
        inserted = load_static_assets_to_db(
            args.asset_csv, session, replace_existing=args.replace_existing
        )
    finally:
        session.close()
    logger.info("Loaded %d assets from %s", inserted, args.asset_csv)
    return inserted


def _ingest_rainfall(args: argparse.Namespace, logger: logging.Logger) -> tuple[int, int]:
    from src.db.session import SessionLocal

    stations = read_rainfall_stations_csv(args.station_csv)
    observations = read_rainfall_observations_csv(args.observation_csv)

    session = SessionLocal()
    try:
        n_stations = load_rainfall_stations_to_db(
            stations, session, replace_existing=args.replace_existing
        )
        n_observations = load_rainfall_observations_to_db(
            observations, session, replace_existing=args.replace_existing
        )
    finally:
        session.close()

    logger.info(
        "Loaded %d rainfall stations and %d rainfall observations",
        n_stations,
        n_observations,
    )
    return n_stations, n_observations


def _ingest_boundaries(args: argparse.Namespace, logger: logging.Logger) -> int:
    from src.db.session import SessionLocal

    records = read_lga_boundaries_file(args.boundary_file)
    session = SessionLocal()
    try:
        n = load_lga_boundaries_to_db(
            records, session, replace_existing=args.replace_existing
        )
    finally:
        session.close()
    logger.info("Loaded %d LGA boundaries", n)
    return n


def main(argv: list[str] | None = None) -> int:
    configure_logging()
    logger = logging.getLogger("ingest_data")
    args = build_parser().parse_args(argv)

    if not (args.assets or args.rainfall or args.boundaries):
        logger.error("Specify at least one of --assets, --rainfall, or --boundaries.")
        return 2

    asset_count = 0
    station_count = 0
    observation_count = 0
    boundary_count = 0

    try:
        if args.replace_existing:
            from src.db.session import SessionLocal

            clear_session = SessionLocal()
            try:
                _clear_for_full_ingest(
                    clear_session,
                    refresh_assets=args.assets,
                    refresh_rainfall=args.rainfall,
                    refresh_boundaries=args.boundaries,
                    logger=logger,
                )
            finally:
                clear_session.close()

        if args.assets:
            asset_count = _ingest_assets(args, logger)
        if args.rainfall:
            station_count, observation_count = _ingest_rainfall(args, logger)
        if args.boundaries:
            boundary_count = _ingest_boundaries(args, logger)
    except Exception as exc:
        logger.error("Ingestion failed: %s", exc)
        return 3

    parts = []
    if args.assets:
        parts.append(f"assets={asset_count}")
    if args.rainfall:
        parts.append(f"stations={station_count}")
        parts.append(f"observations={observation_count}")
    if args.boundaries:
        parts.append(f"boundaries={boundary_count}")
    print(" ".join(parts))
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
