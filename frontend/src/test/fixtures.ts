import type {
  AssetDetail,
  AssetRainfallResponse,
  AssetRiskResponse,
  AssetStationResponse,
  ModelMetadataResponse,
  ModelPredictionDetailResponse,
  ModelPredictionListResponse,
  PortfolioRiskRankingResponse,
  PortfolioSummaryResponse,
  ReportExportResponse,
} from "../types/api";
import type { AssetMapFeatureCollection } from "../types/geojson";

export const summaryFixture: PortfolioSummaryResponse = {
  as_of_date: "2025-12-31",
  simulation_id: "DEFAULT_2025_BASELINE",
  model_name: "rainfall_risk_lgbm",
  model_version: "v1",
  total_assets: 5000,
  total_asset_value: 1_000_000_000,
  total_coverage_limit: 500_000_000,
  average_risk_score: 32.5,
  high_or_severe_assets: 410,
  triggered_assets: 22,
  total_estimated_payout: 750_000,
  average_ml_risk_probability: 0.18,
  risk_band_distribution: [
    {
      risk_band: "Low",
      asset_count: 2500,
      average_risk_score: 12.0,
      total_coverage_limit: 100_000_000,
      total_estimated_payout: 0,
    },
    {
      risk_band: "Medium",
      asset_count: 1800,
      average_risk_score: 35.0,
      total_coverage_limit: 200_000_000,
      total_estimated_payout: 0,
    },
    {
      risk_band: "High",
      asset_count: 600,
      average_risk_score: 60.0,
      total_coverage_limit: 150_000_000,
      total_estimated_payout: 250_000,
    },
    {
      risk_band: "Severe",
      asset_count: 100,
      average_risk_score: 85.0,
      total_coverage_limit: 50_000_000,
      total_estimated_payout: 500_000,
    },
  ],
  industry_summary: [
    {
      industry: "hospitality",
      asset_count: 600,
      average_risk_score: 42,
      high_or_severe_assets: 80,
      triggered_assets: 8,
      total_coverage_limit: 50_000_000,
      total_estimated_payout: 200_000,
    },
    {
      industry: "logistics",
      asset_count: 500,
      average_risk_score: 48,
      high_or_severe_assets: 75,
      triggered_assets: 4,
      total_coverage_limit: 70_000_000,
      total_estimated_payout: 300_000,
    },
  ],
  lga_summary: [],
};

export const rankingFixture: PortfolioRiskRankingResponse = {
  items: [
    {
      rank: 1,
      asset_id: "VIC0001",
      business_type: "warehouse",
      industry: "logistics",
      postcode: "Dandenong",
      lga_code: "LGA21890",
      lga_name: "Greater Dandenong",
      asset_value: 1_500_000,
      coverage_limit: 250_000,
      risk_score: 82,
      risk_band: "Severe",
      rainfall_3d_mm: 215,
      trigger_status: "triggered",
      estimated_payout: 250_000,
      ml_risk_probability: 0.97,
      ml_risk_rank: 1,
      top_risk_driver: "rainfall_percentile",
    },
  ],
  pagination: { limit: 20, offset: 0, total: 1, returned: 1 },
  sort_by: "ml_risk_probability",
  sort_order: "desc",
  as_of_date: "2025-12-31",
  simulation_id: "DEFAULT_2025_BASELINE",
  model_name: "rainfall_risk_lgbm",
  model_version: "v1",
};

export const assetMapFixture: AssetMapFeatureCollection = {
  type: "FeatureCollection",
  features: [
    {
      type: "Feature",
      geometry: { type: "Point", coordinates: [144.96, -37.81] },
      properties: {
        asset_id: "VIC0001",
        postcode: "Melbourne",
        industry: "hospitality",
        risk_band: "Severe",
        risk_score: 82,
        ml_risk_probability: 0.97,
        rainfall_3d_mm: 215,
        estimated_payout: 250_000,
        trigger_status: "triggered",
      },
    },
  ],
};

export const assetDetailFixture: AssetDetail = {
  asset_id: "VIC0001",
  business_type: "warehouse",
  industry: "logistics",
  postcode: "Dandenong",
  latitude: -38.0,
  longitude: 145.2,
  asset_value: 1_500_000,
  coverage_limit: 250_000,
  lga_code: "LGA21890",
  lga_name: "Greater Dandenong",
  risk_score: 82,
  risk_band: "Severe",
  rainfall_3d_mm: 215,
  rainfall_percentile: 0.98,
  extreme_rainfall_flag: true,
  station_id: "ST001",
  station_name: "Dandenong AWS",
  station_distance_km: 4.2,
  station_confidence_weight: 0.96,
  ml_risk_probability: 0.97,
  ml_risk_rank: 1,
  top_risk_driver: "rainfall_percentile",
};

export const assetRiskFixture: AssetRiskResponse = {
  asset_id: "VIC0001",
  as_of_date: "2025-12-31",
  rainfall_extreme_score: 95,
  exposure_weight: 1.2,
  vulnerability_weight: 1.3,
  station_confidence_weight: 0.96,
  raw_score: 142.4,
  risk_score: 82,
  risk_band: "Severe",
};

export const assetRainfallFixture: AssetRainfallResponse = {
  asset_id: "VIC0001",
  station_id: "ST001",
  as_of_date: "2025-12-31",
  rainfall_1d_mm: 80,
  rainfall_3d_mm: 215,
  rainfall_7d_mm: 250,
  rainfall_30d_mm: 410,
  rainfall_percentile: 0.98,
  extreme_rainfall_flag: true,
};

export const assetStationFixture: AssetStationResponse = {
  asset_id: "VIC0001",
  station_id: "ST001",
  station_name: "Dandenong AWS",
  latitude: -38.0,
  longitude: 145.2,
  station_distance_km: 4.2,
  station_confidence_weight: 0.96,
  matched_at: "2026-05-13T00:00:00Z",
};

export const modelMetadataFixture: ModelMetadataResponse = {
  model_name: "rainfall_risk_lgbm",
  model_version: "v1",
  as_of_date: "2025-12-31",
  feature_version: "rainfall_risk_features_v1",
  target_name: "target_extreme_rainfall_event",
  feature_count: 38,
  train_row_count: 4000,
  test_row_count: 1000,
  positive_rate: 0.12,
  metrics: { roc_auc: 0.91, pr_auc: 0.55, accuracy: 0.88 },
  mlflow_run_id: "abc123",
  prediction_count: 5000,
};

export const modelPredictionListFixture: ModelPredictionListResponse = {
  items: [
    {
      asset_id: "VIC0001",
      industry: "logistics",
      postcode: "Dandenong",
      ml_risk_probability: 0.97,
      ml_risk_rank: 1,
      top_risk_driver: "rainfall_percentile",
      risk_band: "Severe",
      risk_score: 82,
      as_of_date: "2025-12-31",
      model_name: "rainfall_risk_lgbm",
      model_version: "v1",
    },
  ],
  pagination: { limit: 20, offset: 0, total: 1, returned: 1 },
  model_name: "rainfall_risk_lgbm",
  model_version: "v1",
  as_of_date: "2025-12-31",
  sort_by: "ml_risk_rank",
  sort_order: "asc",
};

export const modelPredictionDetailFixture: ModelPredictionDetailResponse = {
  ...modelPredictionListFixture.items[0],
  rainfall_3d_mm: 215,
  rainfall_percentile: 0.98,
  extreme_rainfall_flag: true,
};

export const reportExportFixture: ReportExportResponse = {
  report_id:
    "portfolio_report_2025-12-31_DEFAULT_2025_BASELINE_rainfall_risk_lgbm_v1",
  report_title: "Portfolio Risk Report",
  as_of_date: "2025-12-31",
  simulation_id: "DEFAULT_2025_BASELINE",
  model_name: "rainfall_risk_lgbm",
  model_version: "v1",
  feature_version: "rainfall_risk_features_v1",
  output_path:
    "/abs/path/to/backend/artifacts/reports/portfolio_report_2025-12-31_X.html",
  relative_output_path: "backend/artifacts/reports/portfolio_report_2025-12-31_X.html",
  file_size_bytes: 184213,
  created_at: "2026-05-13T12:08:11Z",
  sections: [
    {
      section: "portfolio_summary",
      available: true,
      row_count: 1,
      message: null,
    },
  ],
  warnings: [],
};
