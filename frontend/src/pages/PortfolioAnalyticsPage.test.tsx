import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import {
  modelMetadataFixture,
  modelPredictionListFixture,
  rankingFixture,
  summaryFixture,
} from "../test/fixtures";

vi.mock("../hooks/usePortfolio", () => ({
  usePortfolioSummary: () => ({
    data: summaryFixture,
    isLoading: false,
    error: null,
  }),
  usePortfolioRiskRanking: () => ({
    data: rankingFixture,
    isLoading: false,
    error: null,
  }),
}));

vi.mock("../hooks/useModel", () => ({
  useModelMetadata: () => ({
    data: modelMetadataFixture,
    isLoading: false,
    error: null,
  }),
  useModelPredictions: () => ({
    data: modelPredictionListFixture,
    isLoading: false,
    error: null,
  }),
}));

vi.mock("../hooks/useSimulation", () => ({
  usePayoutSimulationMutation: () => ({
    mutate: vi.fn(),
    isPending: false,
    isError: false,
    error: null,
    data: undefined,
  }),
  useThresholdSensitivityMutation: () => ({
    mutate: vi.fn(),
    isPending: false,
    isError: false,
    error: null,
    data: undefined,
  }),
}));

vi.mock("../hooks/useReportExport", () => ({
  useReportExportMutation: () => ({
    mutate: vi.fn(),
    isPending: false,
    isError: false,
    error: null,
    data: undefined,
  }),
}));

import { PortfolioAnalyticsPage } from "./PortfolioAnalyticsPage";

describe("PortfolioAnalyticsPage", () => {
  it("renders summary cards, charts, tables, simulator, and report panels", () => {
    render(<PortfolioAnalyticsPage />);
    expect(screen.getByText("Total assets")).toBeInTheDocument();
    expect(screen.getByText("Risk band distribution")).toBeInTheDocument();
    expect(
      screen.getByText("Average risk score by industry"),
    ).toBeInTheDocument();
    expect(screen.getByText("Top risk assets")).toBeInTheDocument();
    expect(screen.getByText("Top payout assets")).toBeInTheDocument();
    expect(screen.getByText("Model metadata")).toBeInTheDocument();
    expect(screen.getByText("Model predictions")).toBeInTheDocument();
    expect(screen.getByText("Payout simulator")).toBeInTheDocument();
    expect(screen.getByText("Export HTML report")).toBeInTheDocument();
  });
});
