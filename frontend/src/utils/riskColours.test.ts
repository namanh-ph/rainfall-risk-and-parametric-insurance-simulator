import { describe, expect, it } from "vitest";
import { RISK_BAND_ORDER, getRiskColour, getRiskHex } from "./riskColours";

describe("riskColours", () => {
  it("returns distinct hex per band", () => {
    const hexes = new Set(RISK_BAND_ORDER.map(getRiskHex));
    expect(hexes.size).toBe(RISK_BAND_ORDER.length);
  });

  it("returns unknown colour for null/undefined/invalid input", () => {
    const unknown = getRiskColour(null).hex;
    expect(unknown).toBe(getRiskColour(undefined).hex);
    expect(unknown).toBe(getRiskColour("Mystery" as never).hex);
  });

  it("provides Tailwind bg and text classes per band", () => {
    const colour = getRiskColour("Severe");
    expect(colour.bg).toMatch(/red/);
    expect(colour.text).toMatch(/red/);
  });
});
