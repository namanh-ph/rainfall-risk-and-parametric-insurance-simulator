import { useQuery, type UseQueryResult } from "@tanstack/react-query";
import {
  getAssetDetail,
  getAssetRainfall,
  getAssetRisk,
  getAssetStation,
  getAssets,
  type AssetListParams,
} from "../api/endpoints";
import { queryKeys } from "../api/queryKeys";
import type {
  AssetDetail,
  AssetListResponse,
  AssetRainfallResponse,
  AssetRiskResponse,
  AssetStationResponse,
} from "../types/api";

export function useAssetList(params: AssetListParams): UseQueryResult<AssetListResponse> {
  return useQuery({
    queryKey: queryKeys.assets(params),
    queryFn: () => getAssets(params),
  });
}

export function useAssetDetail(
  assetId: string | null,
  asOfDate?: string,
): UseQueryResult<AssetDetail> {
  return useQuery({
    queryKey: queryKeys.assetDetail(assetId ?? "", asOfDate),
    queryFn: () =>
      getAssetDetail(assetId as string, asOfDate ? { as_of_date: asOfDate } : {}),
    enabled: Boolean(assetId),
  });
}

export function useAssetRisk(
  assetId: string | null,
  asOfDate?: string,
): UseQueryResult<AssetRiskResponse> {
  return useQuery({
    queryKey: queryKeys.assetRisk(assetId ?? "", asOfDate),
    queryFn: () =>
      getAssetRisk(assetId as string, asOfDate ? { as_of_date: asOfDate } : {}),
    enabled: Boolean(assetId),
    retry: false,
  });
}

export function useAssetRainfall(
  assetId: string | null,
  asOfDate?: string,
): UseQueryResult<AssetRainfallResponse> {
  return useQuery({
    queryKey: queryKeys.assetRainfall(assetId ?? "", asOfDate),
    queryFn: () =>
      getAssetRainfall(assetId as string, asOfDate ? { as_of_date: asOfDate } : {}),
    enabled: Boolean(assetId),
    retry: false,
  });
}

export function useAssetStation(
  assetId: string | null,
): UseQueryResult<AssetStationResponse> {
  return useQuery({
    queryKey: queryKeys.assetStation(assetId ?? ""),
    queryFn: () => getAssetStation(assetId as string),
    enabled: Boolean(assetId),
    retry: false,
  });
}
