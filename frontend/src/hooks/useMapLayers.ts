import { useQuery, type UseQueryResult } from "@tanstack/react-query";
import {
  getMapAssets,
  getMapLgas,
  getMapStations,
  type MapAssetsParams,
} from "../api/endpoints";
import { queryKeys } from "../api/queryKeys";
import type {
  AssetMapFeatureCollection,
  LgaMapFeatureCollection,
  StationMapFeatureCollection,
} from "../types/geojson";

export function useMapAssets(
  params: MapAssetsParams = {},
): UseQueryResult<AssetMapFeatureCollection> {
  return useQuery({
    queryKey: queryKeys.mapAssets(params),
    queryFn: () => getMapAssets(params),
  });
}

export function useMapLgas(
  params: { with_aggregates?: boolean; as_of_date?: string } = {},
): UseQueryResult<LgaMapFeatureCollection> {
  return useQuery({
    queryKey: queryKeys.mapLgas(params),
    queryFn: () => getMapLgas(params),
  });
}

export function useMapStations(
  params: { with_aggregates?: boolean } = {},
): UseQueryResult<StationMapFeatureCollection> {
  return useQuery({
    queryKey: queryKeys.mapStations(params),
    queryFn: () => getMapStations(params),
  });
}
