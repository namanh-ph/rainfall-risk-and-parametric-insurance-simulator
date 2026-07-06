import { useMutation, type UseMutationResult } from "@tanstack/react-query";
import { exportReport } from "../api/endpoints";
import type { ReportExportRequest, ReportExportResponse } from "../types/api";

export function useReportExportMutation(): UseMutationResult<
  ReportExportResponse,
  Error,
  ReportExportRequest
> {
  return useMutation({
    mutationFn: (body: ReportExportRequest) => exportReport(body),
  });
}
