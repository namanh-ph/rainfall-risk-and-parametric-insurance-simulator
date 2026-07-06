"""Rule-based rainfall risk scoring"""

from src.risk.bands import assign_risk_band
from src.risk.scoring import (
    build_asset_risk_scoring_query,
    calculate_asset_risk_score_record,
    calculate_exposure_weight,
    calculate_rainfall_extreme_score,
    calculate_raw_risk_score,
    calculate_vulnerability_weight,
    clip_risk_score,
    fetch_asset_risk_scoring_inputs,
    generate_asset_risk_score_records,
    persist_asset_risk_scores,
    run_asset_risk_scoring,
    validate_asset_risk_score_records,
)

__all__ = [
    "assign_risk_band",
    "build_asset_risk_scoring_query",
    "calculate_asset_risk_score_record",
    "calculate_exposure_weight",
    "calculate_rainfall_extreme_score",
    "calculate_raw_risk_score",
    "calculate_vulnerability_weight",
    "clip_risk_score",
    "fetch_asset_risk_scoring_inputs",
    "generate_asset_risk_score_records",
    "persist_asset_risk_scores",
    "run_asset_risk_scoring",
    "validate_asset_risk_score_records",
]
