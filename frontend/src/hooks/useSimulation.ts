import { useMutation, type UseMutationResult } from "@tanstack/react-query";
import { runThresholdSensitivity, simulatePayout } from "../api/endpoints";
import type {
  PayoutSimulationRequest,
  PayoutSimulationResponse,
  ThresholdSensitivityRequest,
  ThresholdSensitivityResponse,
} from "../types/api";

export function usePayoutSimulationMutation(): UseMutationResult<
  PayoutSimulationResponse,
  Error,
  PayoutSimulationRequest
> {
  return useMutation({
    mutationFn: (body: PayoutSimulationRequest) => simulatePayout(body),
  });
}

export function useThresholdSensitivityMutation(): UseMutationResult<
  ThresholdSensitivityResponse,
  Error,
  ThresholdSensitivityRequest
> {
  return useMutation({
    mutationFn: (body: ThresholdSensitivityRequest) =>
      runThresholdSensitivity(body),
  });
}
