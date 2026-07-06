import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import {
  assetDetailFixture,
  assetMapFixture,
  assetRainfallFixture,
  assetRiskFixture,
  assetStationFixture,
  modelPredictionDetailFixture,
  summaryFixture,
} from "../test/fixtures";

vi.mock("../hooks/usePortfolio", () => ({
  usePortfolioSummary: vi.fn(),
  usePortfolioRiskRanking: vi.fn(),
}));

vi.mock("../hooks/useMapLayers", () => ({
  useMapAssets: vi.fn(),
  useMapLgas: () => ({ data: undefined, isLoading: false, error: null }),
  useMapStations: () => ({ data: undefined, isLoading: false, error: null }),
}));

vi.mock("../hooks/useAssets", () => ({
  useAssetDetail: () => ({ data: assetDetailFixture, isLoading: false, error: null }),
  useAssetRisk: () => ({ data: assetRiskFixture, isLoading: false, error: null }),
  useAssetRainfall: () => ({
    data: assetRainfallFixture,
    isLoading: false,
    error: null,
  }),
  useAssetStation: () => ({
    data: assetStationFixture,
    isLoading: false,
    error: null,
  }),
}));

vi.mock("../hooks/useModel", () => ({
  useModelPredictionDetail: () => ({
    data: modelPredictionDetailFixture,
    isLoading: false,
    error: null,
  }),
}));

// Avoid pulling react-leaflet into jsdom; the map is exercised separately
vi.mock("../components/map/RiskMap", () => ({
  RiskMap: () => <div data-testid="risk-map" />,
}));

import { usePortfolioSummary } from "../hooks/usePortfolio";
import { useMapAssets } from "../hooks/useMapLayers";
import { DashboardPage } from "./DashboardPage";

const mockedSummary = vi.mocked(usePortfolioSummary);
const mockedMapAssets = vi.mocked(useMapAssets);

function setLoaded(): void {
  mockedSummary.mockReturnValue({
    data: summaryFixture,
    isLoading: false,
    error: null,
  } as unknown as ReturnType<typeof usePortfolioSummary>);
  mockedMapAssets.mockReturnValue({
    data: assetMapFixture,
    isLoading: false,
    error: null,
  } as unknown as ReturnType<typeof useMapAssets>);
}

function setLoading(): void {
  mockedSummary.mockReturnValue({
    data: undefined,
    isLoading: true,
    error: null,
  } as unknown as ReturnType<typeof usePortfolioSummary>);
  mockedMapAssets.mockReturnValue({
    data: undefined,
    isLoading: true,
    error: null,
  } as unknown as ReturnType<typeof useMapAssets>);
}

function setError(): void {
  const error = new Error("boom");
  mockedSummary.mockReturnValue({
    data: undefined,
    isLoading: false,
    error,
  } as unknown as ReturnType<typeof usePortfolioSummary>);
  mockedMapAssets.mockReturnValue({
    data: undefined,
    isLoading: false,
    error,
  } as unknown as ReturnType<typeof useMapAssets>);
}

describe("DashboardPage", () => {
  it("renders loading state while queries are pending", () => {
    setLoading();
    render(<DashboardPage />);
    expect(
      screen.getByText(/loading portfolio summary/i),
    ).toBeInTheDocument();
  });

  it("renders error state when summary query fails", () => {
    setError();
    render(<DashboardPage />);
    expect(
      screen.getByText(/could not load portfolio summary/i),
    ).toBeInTheDocument();
  });

  it("renders summary cards, filters, and map when data is loaded", () => {
    setLoaded();
    render(<DashboardPage />);
    expect(screen.getByText("Total assets")).toBeInTheDocument();
    expect(screen.getByText(/LGA overlay/i)).toBeInTheDocument();
    expect(screen.getByTestId("risk-map")).toBeInTheDocument();
  });
});
