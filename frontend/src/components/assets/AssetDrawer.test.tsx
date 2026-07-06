import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import {
  assetDetailFixture,
  assetRainfallFixture,
  assetRiskFixture,
  assetStationFixture,
  modelPredictionDetailFixture,
} from "../../test/fixtures";

vi.mock("../../hooks/useAssets", () => ({
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

vi.mock("../../hooks/useModel", () => ({
  useModelPredictionDetail: () => ({
    data: modelPredictionDetailFixture,
    isLoading: false,
    error: null,
  }),
}));

import { AssetDrawer } from "./AssetDrawer";

describe("AssetDrawer", () => {
  it("returns null when no asset is selected", () => {
    const { container } = render(<AssetDrawer assetId={null} onClose={() => {}} />);
    expect(container.firstChild).toBeNull();
  });

  it("renders profile, risk, rainfall, station, and prediction sections", () => {
    render(<AssetDrawer assetId="VIC0001" onClose={() => {}} />);
    expect(screen.getByRole("dialog", { name: /asset details/i })).toBeInTheDocument();
    // Section headings (h3); avoid clashes with field labels of the same name
    const headings = screen.getAllByRole("heading", { level: 3 }).map((h) => h.textContent);
    expect(headings).toEqual(
      expect.arrayContaining([
        "Profile",
        "Risk",
        "Rainfall",
        "Station",
        "ML prediction",
      ]),
    );
    // Field values from fixtures should render
    expect(screen.getByText("Dandenong")).toBeInTheDocument();
    expect(screen.getByText("Dandenong AWS")).toBeInTheDocument();
    expect(screen.getByText("rainfall_percentile")).toBeInTheDocument();
  });
});
