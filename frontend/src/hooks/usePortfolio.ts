import { useQuery, type UseQueryResult } from "@tanstack/react-query";
import {
  getPortfolioRiskRanking,
  getPortfolioSummary,
  type PortfolioRiskRankingParams,
  type PortfolioSummaryParams,
} from "../api/endpoints";
import { queryKeys } from "../api/queryKeys";
import type {
  PortfolioRiskRankingResponse,
  PortfolioSummaryResponse,
} from "../types/api";

export function usePortfolioSummary(
  params: PortfolioSummaryParams = {},
): UseQueryResult<PortfolioSummaryResponse> {
  return useQuery({
    queryKey: queryKeys.portfolioSummary(params),
    queryFn: () => getPortfolioSummary(params),
  });
}

export function usePortfolioRiskRanking(
  params: PortfolioRiskRankingParams,
): UseQueryResult<PortfolioRiskRankingResponse> {
  return useQuery({
    queryKey: queryKeys.portfolioRiskRanking(params),
    queryFn: () => getPortfolioRiskRanking(params),
  });
}
