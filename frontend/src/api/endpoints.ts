/**
 * Typed wrappers around the `/api/v1` backend routes. Each
 * function returns a fully-typed Promise and is the only place the
 * frontend talks to the backend. Hooks in `src/hooks/` compose these
 */

import { apiFetch, type QueryParams } from "./client";
import type {
  AssetDetail,
  AssetListResponse,
  AssetRainfallResponse,
  AssetRiskResponse,
  AssetStationResponse,
  DbHealthResponse,
  HealthResponse,
  ModelMetadataResponse,
  ModelPredictionDetailResponse,
  ModelPredictionListResponse,
  PayoutSimulationRequest,
  PayoutSimulationResponse,
  PortfolioRiskRankingResponse,
  PortfolioSummaryResponse,
  ReportExportRequest,
  ReportExportResponse,
  ThresholdSensitivityRequest,
  ThresholdSensitivityResponse,
} from "../types/api";
import type {
  AssetMapFeatureCollection,
  LgaMapFeatureCollection,
  StationMapFeatureCollection,
} from "../types/geojson";

// â”€â”€ Health â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
export function getHealth(): Promise<HealthResponse> {
  return apiFetch<HealthResponse>("/health");
}

export function getDbHealth(): Promise<DbHealthResponse> {
  return apiFetch<DbHealthResponse>("/health/db");
}

// â”€â”€ Assets â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
export interface AssetListParams extends QueryParams {
  limit?: number;
  offset?: number;
  industry?: string;
  postcode?: string;
  lga_code?: string;
  risk_band?: string;
  min_risk_score?: number;
  max_risk_score?: number;
  as_of_date?: string;
  sort_by?: string;
  sort_order?: string;
}

export function getAssets(params: AssetListParams = {}): Promise<AssetListResponse> {
  return apiFetch<AssetListResponse>("/assets", { query: params });
}

export function getAssetDetail(
  assetId: string,
  params: { as_of_date?: string } = {},
): Promise<AssetDetail> {
  return apiFetch<AssetDetail>(`/assets/${encodeURIComponent(assetId)}`, {
    query: params,
  });
}

export function getAssetRisk(
  assetId: string,
  params: { as_of_date?: string } = {},
): Promise<AssetRiskResponse> {
  return apiFetch<AssetRiskResponse>(
    `/assets/${encodeURIComponent(assetId)}/risk`,
    { query: params },
  );
}

export function getAssetRainfall(
  assetId: string,
  params: { as_of_date?: string } = {},
): Promise<AssetRainfallResponse> {
  return apiFetch<AssetRainfallResponse>(
    `/assets/${encodeURIComponent(assetId)}/rainfall`,
    { query: params },
  );
}

export function getAssetStation(assetId: string): Promise<AssetStationResponse> {
  return apiFetch<AssetStationResponse>(
    `/assets/${encodeURIComponent(assetId)}/station`,
  );
}

// â”€â”€ Map (GeoJSON) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
export interface MapAssetsParams extends QueryParams {
  limit?: number;
  industry?: string;
  risk_band?: string;
  as_of_date?: string;
  simulation_id?: string;
  model_name?: string;
  model_version?: string;
}

export function getMapAssets(
  params: MapAssetsParams = {},
): Promise<AssetMapFeatureCollection> {
  return apiFetch<AssetMapFeatureCollection>("/map/assets", { query: params });
}

export function getMapLgas(
  params: { with_aggregates?: boolean; as_of_date?: string } = {},
): Promise<LgaMapFeatureCollection> {
  return apiFetch<LgaMapFeatureCollection>("/map/lgas", { query: params });
}

export function getMapStations(
  params: { with_aggregates?: boolean } = {},
): Promise<StationMapFeatureCollection> {
  return apiFetch<StationMapFeatureCollection>("/map/stations", { query: params });
}

// â”€â”€ Portfolio â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
export interface PortfolioSummaryParams extends QueryParams {
  as_of_date?: string;
  simulation_id?: string;
  model_name?: string;
  model_version?: string;
}

export function getPortfolioSummary(
  params: PortfolioSummaryParams = {},
): Promise<PortfolioSummaryResponse> {
  return apiFetch<PortfolioSummaryResponse>("/portfolio/summary", {
    query: params,
  });
}

export interface PortfolioRiskRankingParams extends QueryParams {
  limit?: number;
  offset?: number;
  as_of_date?: string;
  simulation_id?: string;
  model_name?: string;
  model_version?: string;
  risk_band?: string;
  industry?: string;
  lga_code?: string;
  triggered_only?: boolean;
  sort_by?: string;
  sort_order?: string;
}

export function getPortfolioRiskRanking(
  params: PortfolioRiskRankingParams = {},
): Promise<PortfolioRiskRankingResponse> {
  return apiFetch<PortfolioRiskRankingResponse>("/portfolio/risk-ranking", {
    query: params,
  });
}

// â”€â”€ Simulation (mutating) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
export function simulatePayout(
  body: PayoutSimulationRequest,
): Promise<PayoutSimulationResponse> {
  return apiFetch<PayoutSimulationResponse>("/simulate/payout", {
    method: "POST",
    body,
  });
}

export function runThresholdSensitivity(
  body: ThresholdSensitivityRequest,
): Promise<ThresholdSensitivityResponse> {
  return apiFetch<ThresholdSensitivityResponse>("/simulate/threshold-sensitivity", {
    method: "POST",
    body,
  });
}

// â”€â”€ Model â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
export interface ModelMetadataParams extends QueryParams {
  as_of_date?: string;
  feature_version?: string;
  model_name?: string;
  model_version?: string;
}

export function getModelMetadata(
  params: ModelMetadataParams = {},
): Promise<ModelMetadataResponse> {
  return apiFetch<ModelMetadataResponse>("/model/metadata", { query: params });
}

export interface ModelPredictionsParams extends QueryParams {
  limit?: number;
  offset?: number;
  as_of_date?: string;
  model_name?: string;
  model_version?: string;
  risk_band?: string;
  industry?: string;
  lga_code?: string;
  sort_by?: string;
  sort_order?: string;
}

export function getModelPredictions(
  params: ModelPredictionsParams = {},
): Promise<ModelPredictionListResponse> {
  return apiFetch<ModelPredictionListResponse>("/model/predictions", {
    query: params,
  });
}

export function getModelPredictionDetail(
  assetId: string,
  params: { as_of_date?: string; model_name?: string; model_version?: string } = {},
): Promise<ModelPredictionDetailResponse> {
  return apiFetch<ModelPredictionDetailResponse>(
    `/model/predictions/${encodeURIComponent(assetId)}`,
    { query: params },
  );
}

// â”€â”€ Reports (mutating filesystem only) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
export function exportReport(
  body: ReportExportRequest,
): Promise<ReportExportResponse> {
  return apiFetch<ReportExportResponse>("/reports/export", {
    method: "POST",
    body,
  });
}
