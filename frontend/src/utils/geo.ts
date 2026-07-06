import type { LatLngTuple } from "leaflet";
import type { Position } from "../types/geojson";

/**
 * Convert a GeoJSON `[lon, lat]` position into Leaflet's `[lat, lon]`
 * tuple. Use this everywhere coordinates cross the GeoJSON/Leaflet
 * boundary so the order bug never sneaks in
 */
export function positionToLatLng(position: Position): LatLngTuple {
  return [position[1], position[0]];
}

export function latLngToPosition(latLng: LatLngTuple): Position {
  return [latLng[1], latLng[0]];
}

/**
 * Convert a polygon ring (array of GeoJSON positions) into an array of
 * Leaflet LatLng tuples
 */
export function positionsToLatLngs(positions: Position[]): LatLngTuple[] {
  return positions.map(positionToLatLng);
}
