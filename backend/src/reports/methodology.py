"""Static methodology notes embedded in the HTML report."""

from __future__ import annotations

from typing import Any


def get_methodology_notes() -> dict[str, Any]:
    """Return the structured methodology block for the portfolio report."""
    return {
        "title": "Methodology",
        "data_disclaimer": (
            "This report is built from rainfall observations sourced from "
            "the Bureau of Meteorology, Victorian LGA boundaries published "
            "by the Australian Bureau of Statistics, and the asset "
            "portfolio loaded from data/assets.csv."
        ),
        "sections": [
            {
                "heading": "Asset portfolio",
                "body": (
                    "5 000 Victorian SME / property assets are loaded from "
                    "data/assets.csv. The portfolio is "
                    "spatially distributed across inner Melbourne, the "
                    "industrial corridor, growth corridors, regional cities, "
                    "agricultural towns, coastal-tourism towns, Gippsland, "
                    "and the high-rainfall east. Only the nine canonical "
                    "fields are persisted into the assets table; ~35 wider "
                    "modelling/policy fields remain in the CSV for analytics."
                ),
            },
            {
                "heading": "Rainfall and LGA data",
                "body": (
                    "Rainfall is ingested as 15 Victorian Bureau of "
                    "Meteorology stations and one year of daily "
                    "observations. LGA boundaries are loaded from a "
                    "Victorian LGA polygon set published by the Australian "
                    "Bureau of Statistics."
                ),
            },
            {
                "heading": "Asset-to-station matching",
                "body": (
                    "Each asset is mapped to its nearest rainfall station "
                    "using PostGIS geography distance. The persisted "
                    "station_confidence_weight is "
                    "max(0.50, 1 - station_distance_km / 100)."
                ),
            },
            {
                "heading": "Asset-to-LGA assignment",
                "body": (
                    "Each asset is assigned to a Victorian LGA using "
                    "ST_Covers and ST_Intersects, with an optional "
                    "nearest-LGA fallback (default cap 25 km) for assets "
                    "near simplified-rectangle boundary gaps."
                ),
            },
            {
                "heading": "Rainfall feature engineering",
                "body": (
                    "rainfall_features is built per (asset_id, as_of_date) "
                    "using trailing 1/3/7/30-day totals, station-historical "
                    "p95 / p99 / max over a 365-day lookback, a rolling-3d "
                    "percentile rank, and an extreme_rainfall_flag set when "
                    "rainfall_percentile >= 0.95 OR rainfall_3d_mm >= "
                    "3 * rainfall_p95_station."
                ),
            },
            {
                "heading": "Rule-based risk scoring",
                "body": (
                    "asset_risk_scores stores raw_score = "
                    "rainfall_extreme_score * exposure_weight * "
                    "vulnerability_weight * station_confidence_weight, "
                    "clipped to [0, 100]. Bands are Low [0, 25), "
                    "Medium [25, 50), High [50, 75), Severe [75, 100]."
                ),
            },
            {
                "heading": "Parametric payout thresholds",
                "body": (
                    "The canonical payout table is rainfall_3d_mm < 100 "
                    "-> 0.0, [100, 150) -> 0.2, [150, 200) -> 0.5, "
                    ">= 200 -> 1.0. estimated_payout = coverage_limit * "
                    "coverage_multiplier * payout_rate. Risk score / band "
                    "do not influence payout calculation."
                ),
            },
            {
                "heading": "Threshold sensitivity",
                "body": (
                    "Sensitivity scenarios use compact deterministic "
                    "simulation_ids (SWEEP_2025_T060, SWEEP_2025_T040, "
                    "SWEEP_2025_T020) and lower demonstration thresholds. "
                    "Coverage-multiplier sensitivity scenarios "
                    "(MULT_2025_X075 .. MULT_2025_X150) hold thresholds "
                    "constant and scale only estimated_payout."
                ),
            },
            {
                "heading": "ML dataset construction",
                "body": (
                    "model_training_data is built per "
                    "(asset_id, as_of_date, feature_version). The default "
                    "feature_version is rainfall_risk_features_v1; the "
                    "binary target target_extreme_rainfall_event is "
                    "derived from rainfall severity and is independent of "
                    "payout_results and risk_score."
                ),
            },
            {
                "heading": "LightGBM training",
                "body": (
                    "A LightGBM binary classifier is trained on the "
                    "engineered feature payload with deterministic "
                    "train/test splitting (asset_id-hash, seed 42), "
                    "scale_pos_weight class-imbalance handling, and "
                    "MLflow logging when available. Local artefacts "
                    "(model.pkl, metadata.json, metrics.json, "
                    "feature_names.json, feature_importance.csv) are "
                    "saved under backend/artifacts/models/."
                ),
            },
            {
                "heading": "Batch prediction",
                "body": (
                    "model_predictions stores per-asset ml_risk_probability "
                    "and a deterministic ml_risk_rank. top_risk_driver is "
                    "the highest-importance feature with a non-null value "
                    "for the asset; SHAP is intentionally not used."
                ),
            },
            {
                "heading": "Limitations",
                "body": (
                    "Because the rainfall sample is one year long, "
                    "canonical 100 / 150 / 200 mm three-day payout "
                    "thresholds rarely fire — sensitivity scenarios lower "
                    "the bar to show how payouts respond to threshold "
                    "choice. Where LGA polygons overlap, the asset-to-LGA "
                    "join breaks ties deterministically by priority, "
                    "distance, and lga_code."
                ),
            },
        ],
    }


__all__ = ["get_methodology_notes"]
