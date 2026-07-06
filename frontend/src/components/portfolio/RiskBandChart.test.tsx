import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { summaryFixture } from "../../test/fixtures";
import { RiskBandChart } from "./RiskBandChart";

describe("RiskBandChart", () => {
  it("renders the chart container with the heading", () => {
    render(<RiskBandChart data={summaryFixture.risk_band_distribution} />);
    expect(screen.getByText("Risk band distribution")).toBeInTheDocument();
    expect(screen.getByTestId("risk-band-chart")).toBeInTheDocument();
  });

  it("renders without crashing on empty data", () => {
    render(<RiskBandChart data={[]} />);
    expect(screen.getByText("Risk band distribution")).toBeInTheDocument();
  });
});
