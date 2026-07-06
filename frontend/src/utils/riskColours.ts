import type { RiskBand } from "../types/api";

export interface RiskColour {
  /** Hex used by Leaflet markers and Recharts cells */
  hex: string;
  /** Tailwind-friendly background class for badges and table rows */
  bg: string;
  /** Tailwind-friendly text class */
  text: string;
}

const UNKNOWN: RiskColour = {
  hex: "#64748b",
  bg: "bg-slate-100",
  text: "text-slate-700",
};

const PALETTE: Record<RiskBand, RiskColour> = {
  Low: { hex: "#22c55e", bg: "bg-green-100", text: "text-green-800" },
  Medium: { hex: "#f59e0b", bg: "bg-amber-100", text: "text-amber-800" },
  High: { hex: "#fb923c", bg: "bg-orange-100", text: "text-orange-800" },
  Severe: { hex: "#ef4444", bg: "bg-red-100", text: "text-red-800" },
};

export function getRiskColour(band: RiskBand | string | null | undefined): RiskColour {
  if (band && (band as RiskBand) in PALETTE) {
    return PALETTE[band as RiskBand];
  }
  return UNKNOWN;
}

export function getRiskHex(band: RiskBand | string | null | undefined): string {
  return getRiskColour(band).hex;
}

export const RISK_BAND_ORDER: RiskBand[] = ["Low", "Medium", "High", "Severe"];
