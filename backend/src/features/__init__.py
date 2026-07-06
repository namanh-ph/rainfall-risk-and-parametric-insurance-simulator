"""Rainfall feature engineering"""

from src.features.rainfall_features import (
    build_asset_rainfall_feature_query,
    calculate_asset_rainfall_feature_record,
    calculate_percentile_rank,
    calculate_station_daily_statistics,
    calculate_station_rolling_3d_totals,
    calculate_trailing_rainfall_totals,
    fetch_asset_station_observations_for_features,
    generate_rainfall_feature_records,
    persist_rainfall_features,
    run_rainfall_feature_generation,
    validate_rainfall_feature_records,
)

__all__ = [
    "build_asset_rainfall_feature_query",
    "calculate_asset_rainfall_feature_record",
    "calculate_percentile_rank",
    "calculate_station_daily_statistics",
    "calculate_station_rolling_3d_totals",
    "calculate_trailing_rainfall_totals",
    "fetch_asset_station_observations_for_features",
    "generate_rainfall_feature_records",
    "persist_rainfall_features",
    "run_rainfall_feature_generation",
    "validate_rainfall_feature_records",
]
