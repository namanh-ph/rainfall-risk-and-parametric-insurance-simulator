/**
 * Centralised TanStack Query keys. Hooks use these so cache
 * invalidation lives in one place
 */

export const queryKeys = {
  health: () => ["health"] as const,
  dbHealth: () => ["health", "db"] as const,
  assets: (params: unknown) => ["assets", params] as const,
  assetDetail: (assetId: string, asOfDate?: string) =>
    ["assets", assetId, "detail", asOfDate] as const,
  assetRisk: (assetId: string, asOfDate?: string) =>
    ["assets", assetId, "risk", asOfDate] as const,
  assetRainfall: (assetId: string, asOfDate?: string) =>
    ["assets", assetId, "rainfall", asOfDate] as const,
  assetStation: (assetId: string) =>
    ["assets", assetId, "station"] as const,
  mapAssets: (params: unknown) => ["map", "assets", params] as const,
  mapLgas: (params: unknown) => ["map", "lgas", params] as const,
  mapStations: (params: unknown) => ["map", "stations", params] as const,
  portfolioSummary: (params: unknown) => ["portfolio", "summary", params] as const,
  portfolioRiskRanking: (params: unknown) =>
    ["portfolio", "risk-ranking", params] as const,
  modelMetadata: (params: unknown) => ["model", "metadata", params] as const,
  modelPredictions: (params: unknown) => ["model", "predictions", params] as const,
  modelPredictionDetail: (assetId: string, params: unknown) =>
    ["model", "predictions", assetId, params] as const,
};
