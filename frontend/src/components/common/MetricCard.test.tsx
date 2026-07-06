import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { MetricCard } from "./MetricCard";

describe("MetricCard", () => {
  it("renders the title and value", () => {
    render(<MetricCard title="Total assets" value="5,000" hint="As of 2025" />);
    expect(screen.getByText("Total assets")).toBeInTheDocument();
    expect(screen.getByText("5,000")).toBeInTheDocument();
    expect(screen.getByText("As of 2025")).toBeInTheDocument();
  });

  it("falls back to the brand accent when no accent is supplied", () => {
    const { container } = render(<MetricCard title="X" value="1" />);
    const valueNode = container.querySelector("p:nth-child(2)");
    expect(valueNode).not.toBeNull();
    expect(valueNode?.className).toContain("text-brand");
  });
});
