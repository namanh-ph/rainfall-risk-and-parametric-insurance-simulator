/**
 * Minimal GeoJSON types compatible with react-leaflet and the backend
 * GeoJSON map endpoints (`/api/v1/map/*`).
 *
 * The backend always returns RFC 7946 `[longitude, latitude]` coordinates
 */

export type Position = [number, number];

export interface PointGeometry {
  type: "Point";
  coordinates: Position;
}

export interface PolygonGeometry {
  type: "Polygon";
  coordinates: Position[][];
}

export interface MultiPolygonGeometry {
  type: "MultiPolygon";
  coordinates: Position[][][];
}

export type Geometry = PointGeometry | PolygonGeometry | MultiPolygonGeometry;

export interface Feature<G extends Geometry = Geometry, P = Record<string, unknown>> {
  type: "Feature";
  geometry: G;
  properties: P;
  id?: string | number;
}

export interface FeatureCollection<
  G extends Geometry = Geometry,
  P = Record<string, unknown>,
> {
  type: "FeatureCollection";
  features: Feature<G, P>[];
}

export interface AssetMapFeatureProperties {
  asset_id: string;
  business_type?: string;
  industry?: string;
  postcode?: string;
  lga_code?: string | null;
  lga_name?: string | null;
  asset_value?: number;
  coverage_limit?: number;
  risk_score?: number | null;
  risk_band?: string | null;
  rainfall_3d_mm?: number | null;
  estimated_payout?: number | null;
  trigger_status?: string | null;
  ml_risk_probability?: number | null;
  ml_risk_rank?: number | null;
}

export interface LgaMapFeatureProperties {
  lga_code: string;
  lga_name?: string | null;
  asset_count?: number | null;
  average_risk_score?: number | null;
  high_or_severe_assets?: number | null;
}

export interface StationMapFeatureProperties {
  station_id: string;
  station_name?: string | null;
  elevation_m?: number | null;
  asset_match_count?: number | null;
  data_source?: string | null;
}

export type AssetMapFeatureCollection = FeatureCollection<
  PointGeometry,
  AssetMapFeatureProperties
>;
export type LgaMapFeatureCollection = FeatureCollection<
  PolygonGeometry | MultiPolygonGeometry,
  LgaMapFeatureProperties
>;
export type StationMapFeatureCollection = FeatureCollection<
  PointGeometry,
  StationMapFeatureProperties
>;
