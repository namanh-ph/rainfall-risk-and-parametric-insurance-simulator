import { useQuery, type UseQueryResult } from "@tanstack/react-query";
import {
  getModelMetadata,
  getModelPredictionDetail,
  getModelPredictions,
  type ModelMetadataParams,
  type ModelPredictionsParams,
} from "../api/endpoints";
import { queryKeys } from "../api/queryKeys";
import type {
  ModelMetadataResponse,
  ModelPredictionDetailResponse,
  ModelPredictionListResponse,
} from "../types/api";

export function useModelMetadata(
  params: ModelMetadataParams = {},
): UseQueryResult<ModelMetadataResponse> {
  return useQuery({
    queryKey: queryKeys.modelMetadata(params),
    queryFn: () => getModelMetadata(params),
  });
}

export function useModelPredictions(
  params: ModelPredictionsParams,
): UseQueryResult<ModelPredictionListResponse> {
  return useQuery({
    queryKey: queryKeys.modelPredictions(params),
    queryFn: () => getModelPredictions(params),
  });
}

export function useModelPredictionDetail(
  assetId: string | null,
  params: { as_of_date?: string; model_name?: string; model_version?: string } = {},
): UseQueryResult<ModelPredictionDetailResponse> {
  return useQuery({
    queryKey: queryKeys.modelPredictionDetail(assetId ?? "", params),
    queryFn: () => getModelPredictionDetail(assetId as string, params),
    enabled: Boolean(assetId),
    retry: false,
  });
}
