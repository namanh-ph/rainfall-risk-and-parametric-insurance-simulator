import type { RiskBand } from "../types/api";

export const DEFAULT_AS_OF_DATE = "2025-12-31";
export const DEFAULT_SIMULATION_ID = "DEFAULT_2025_BASELINE";
export const DEFAULT_MODEL_NAME = "rainfall_risk_lgbm";
export const DEFAULT_MODEL_VERSION = "v1";
export const DEFAULT_FEATURE_VERSION = "rainfall_risk_features_v1";

export const VICTORIA_CENTER: [number, number] = [-37.0, 144.5];
export const VICTORIA_INITIAL_ZOOM = 6;

export const RISK_BANDS: RiskBand[] = ["Low", "Medium", "High", "Severe"];

export const INDUSTRY_FILTER_OPTIONS = [
  "agriculture",
  "construction",
  "hospitality",
  "logistics",
  "manufacturing",
  "professional_services",
  "retail",
  "storage",
  "technology",
  "tourism",
];
