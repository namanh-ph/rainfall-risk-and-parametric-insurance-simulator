/**
 * TypeScript mirror of the backend Pydantic schemas in
 * `backend/src/schemas/*`. Keep field names and nullability identical to
 * the API contracts documented in the API contracts.
 */

export type RiskBand = "Low" | "Medium" | "High" | "Severe";

export type TriggerStatus = "triggered" | "not_triggered";

export interface PaginationMeta {
  limit: number;
  offset: number;
  total: number;
  returned: number;
}

export interface ApiErrorEnvelope {
  error?: string;
  detail?: string | Record<string, unknown>;
}

// â”€â”€ Health â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
export interface HealthResponse {
  status: string;
  service?: string;
  environment?: string;
}

export interface DbHealthResponse {
  status: string;
  database?: string;
  postgis?: string;
  postgis_version?: string | null;
}

// â”€â”€ Assets â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
export interface AssetListItem {
  asset_id: string;
  business_type: string;
  industry: string;
  postcode: string;
  latitude: number;
  longitude: number;
  asset_value: number;
  annual_revenue?: number | null;
  coverage_limit: number;
  lga_code?: string | null;
  lga_name?: string | null;
  risk_score?: number | null;
  risk_band?: RiskBand | null;
  rainfall_3d_mm?: number | null;
  station_id?: string | null;
  station_distance_km?: number | null;
  ml_risk_probability?: number | null;
  ml_risk_rank?: number | null;
}

export interface AssetListResponse {
  items: AssetListItem[];
  pagination: PaginationMeta;
}

export interface AssetDetail {
  asset_id: string;
  business_type: string;
  industry: string;
  postcode: string;
  latitude: number;
  longitude: number;
  asset_value: number;
  annual_revenue?: number | null;
  coverage_limit: number;
  lga_code?: string | null;
  lga_name?: string | null;
  risk_score?: number | null;
  risk_band?: RiskBand | null;
  rainfall_1d_mm?: number | null;
  rainfall_3d_mm?: number | null;
  rainfall_7d_mm?: number | null;
  rainfall_30d_mm?: number | null;
  rainfall_percentile?: number | null;
  extreme_rainfall_flag?: boolean | null;
  station_id?: string | null;
  station_name?: string | null;
  station_distance_km?: number | null;
  station_confidence_weight?: number | null;
  ml_risk_probability?: number | null;
  ml_risk_rank?: number | null;
  top_risk_driver?: string | null;
}

export interface AssetRiskResponse {
  asset_id: string;
  as_of_date: string;
  rainfall_extreme_score: number;
  exposure_weight: number;
  vulnerability_weight: number;
  station_confidence_weight: number;
  raw_score: number;
  risk_score: number;
  risk_band: RiskBand;
}

export interface AssetRainfallResponse {
  asset_id: string;
  station_id: string;
  as_of_date: string;
  rainfall_1d_mm: number;
  rainfall_3d_mm: number;
  rainfall_7d_mm: number;
  rainfall_30d_mm: number;
  rainfall_p95_station?: number | null;
  rainfall_p99_station?: number | null;
  rainfall_percentile?: number | null;
  max_365d_rainfall_mm?: number | null;
  days_above_p95_365d?: number | null;
  extreme_rainfall_flag: boolean;
}

export interface AssetStationResponse {
  asset_id: string;
  station_id: string;
  station_name: string;
  latitude: number;
  longitude: number;
  station_distance_km: number;
  station_confidence_weight: number;
  matched_at: string;
  data_source?: string | null;
}

// â”€â”€ Portfolio â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
export interface RiskBandDistributionItem {
  risk_band: RiskBand;
  asset_count: number;
  average_risk_score?: number | null;
  total_coverage_limit: number;
  total_estimated_payout: number;
}

export interface IndustryRiskSummaryItem {
  industry: string;
  asset_count: number;
  average_risk_score?: number | null;
  high_or_severe_assets: number;
  triggered_assets: number;
  total_coverage_limit: number;
  total_estimated_payout: number;
}

export interface LgaRiskSummaryItem {
  lga_code: string;
  lga_name?: string | null;
  asset_count: number;
  average_risk_score?: number | null;
  high_or_severe_assets: number;
  triggered_assets: number;
  total_coverage_limit: number;
  total_estimated_payout: number;
}

export interface PortfolioSummaryResponse {
  as_of_date: string;
  simulation_id: string;
  model_name: string;
  model_version: string;
  total_assets: number;
  total_asset_value: number;
  total_coverage_limit: number;
  average_risk_score?: number | null;
  high_or_severe_assets: number;
  triggered_assets: number;
  total_estimated_payout: number;
  average_ml_risk_probability?: number | null;
  risk_band_distribution: RiskBandDistributionItem[];
  industry_summary: IndustryRiskSummaryItem[];
  lga_summary: LgaRiskSummaryItem[];
}

export interface PortfolioRiskRankingItem {
  rank: number;
  asset_id: string;
  business_type: string;
  industry: string;
  postcode: string;
  lga_code?: string | null;
  lga_name?: string | null;
  asset_value: number;
  coverage_limit: number;
  risk_score?: number | null;
  risk_band?: RiskBand | null;
  rainfall_3d_mm?: number | null;
  rainfall_percentile?: number | null;
  extreme_rainfall_flag?: boolean | null;
  trigger_status?: string | null;
  estimated_payout?: number | null;
  ml_risk_probability?: number | null;
  ml_risk_rank?: number | null;
  top_risk_driver?: string | null;
}

export interface PortfolioRiskRankingResponse {
  items: PortfolioRiskRankingItem[];
  pagination: PaginationMeta;
  sort_by: string;
  sort_order: string;
  as_of_date: string;
  simulation_id: string;
  model_name: string;
  model_version: string;
}

// â”€â”€ Simulation â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
export interface PayoutSimulationRequest {
  as_of_date?: string;
  simulation_id?: string;
  simulation_name?: string;
  coverage_multiplier?: number;
  asset_ids?: string[] | null;
  replace_existing?: boolean;
  include_risk_band?: boolean;
}

export interface PayoutSimulationResponse {
  simulation_id: string;
  simulation_name: string;
  as_of_date: string;
  coverage_multiplier: number;
  assets_considered: number;
  feature_records_available: number;
  payout_records_generated: number;
  payout_records_inserted: number;
  triggered_assets: number;
  not_triggered_assets: number;
  total_coverage_limit: number;
  total_estimated_payout: number;
  average_payout_rate?: number | null;
  replace_existing: boolean;
}

export type SensitivityMode = "thresholds" | "coverage_multipliers" | "combined";

export interface ThresholdSensitivityRequest {
  as_of_date?: string;
  asset_ids?: string[] | null;
  mode?: SensitivityMode;
  replace_existing?: boolean;
  include_risk_band?: boolean;
}

export interface ThresholdSensitivityScenarioResponse {
  simulation_id: string;
  simulation_name: string;
  coverage_multiplier: number;
  payout_records_generated: number;
  payout_records_inserted: number;
  asset_count: number;
  triggered_assets: number;
  not_triggered_assets: number;
  trigger_rate: number;
  total_coverage_limit: number;
  total_estimated_payout: number;
  average_payout_rate: number;
}

export interface ThresholdSensitivityResponse {
  as_of_date: string;
  mode: SensitivityMode;
  scenario_count: number;
  scenarios: ThresholdSensitivityScenarioResponse[];
  replace_existing: boolean;
}

// â”€â”€ Model â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
export interface ModelMetadataResponse {
  model_name: string;
  model_version: string;
  as_of_date: string;
  feature_version?: string | null;
  target_name?: string | null;
  artifact_path?: string | null;
  metrics?: Record<string, number | null> | null;
  feature_count?: number | null;
  train_row_count?: number | null;
  test_row_count?: number | null;
  positive_count?: number | null;
  negative_count?: number | null;
  positive_rate?: number | null;
  mlflow_logged?: boolean | null;
  mlflow_run_id?: string | null;
  prediction_count: number;
  created_at?: string | null;
}

export interface ModelPredictionItem {
  asset_id: string;
  business_type?: string | null;
  industry?: string | null;
  postcode?: string | null;
  lga_code?: string | null;
  lga_name?: string | null;
  risk_score?: number | null;
  risk_band?: RiskBand | null;
  ml_risk_probability: number;
  ml_risk_rank?: number | null;
  top_risk_driver?: string | null;
  as_of_date: string;
  model_name: string;
  model_version: string;
}

export interface ModelPredictionListResponse {
  items: ModelPredictionItem[];
  pagination: PaginationMeta;
  model_name: string;
  model_version: string;
  as_of_date: string;
  sort_by: string;
  sort_order: string;
}

export interface ModelPredictionDetailResponse extends ModelPredictionItem {
  rainfall_3d_mm?: number | null;
  rainfall_percentile?: number | null;
  extreme_rainfall_flag?: boolean | null;
}

// â”€â”€ Reports â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
export interface ReportExportRequest {
  as_of_date?: string;
  simulation_id?: string;
  model_name?: string;
  model_version?: string;
  feature_version?: string;
  report_title?: string;
  output_filename?: string | null;
  include_methodology?: boolean;
  include_top_assets?: boolean;
  top_n?: number;
}

export interface ReportSectionStatus {
  section: string;
  available: boolean;
  row_count: number;
  message?: string | null;
}

export interface ReportExportResponse {
  report_id: string;
  report_title: string;
  as_of_date: string;
  simulation_id: string;
  model_name: string;
  model_version: string;
  feature_version: string;
  output_path: string;
  relative_output_path: string;
  file_size_bytes: number;
  created_at: string;
  sections: ReportSectionStatus[];
  warnings: string[];
}
