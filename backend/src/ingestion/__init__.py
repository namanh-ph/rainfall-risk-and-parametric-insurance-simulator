"""Data ingestion: asset CSV loader, rainfall ingestion, LGA boundaries.

This package reads the files under ``data/`` and loads them into the
PostGIS database. It does not generate rows.
"""

from src.ingestion.assets import (
    load_static_assets_to_db,
    project_asset_record_for_db,
    read_static_assets_csv,
    validate_static_asset_records,
)
from src.ingestion.boundaries import (
    load_lga_boundaries_to_db,
    project_lga_boundary_record_for_db,
    read_lga_boundaries_csv,
    read_lga_boundaries_file,
    read_lga_boundaries_geojson,
    validate_lga_boundary_records,
)
from src.ingestion.rainfall import (
    load_rainfall_observations_to_db,
    load_rainfall_stations_to_db,
    read_rainfall_observations_csv,
    read_rainfall_stations_csv,
    validate_rainfall_observation_records,
    validate_rainfall_station_records,
)

__all__ = [
    "load_lga_boundaries_to_db",
    "load_rainfall_observations_to_db",
    "load_rainfall_stations_to_db",
    "load_static_assets_to_db",
    "project_asset_record_for_db",
    "project_lga_boundary_record_for_db",
    "read_lga_boundaries_csv",
    "read_lga_boundaries_file",
    "read_lga_boundaries_geojson",
    "read_rainfall_observations_csv",
    "read_rainfall_stations_csv",
    "read_static_assets_csv",
    "validate_lga_boundary_records",
    "validate_rainfall_observation_records",
    "validate_rainfall_station_records",
    "validate_static_asset_records",
]
