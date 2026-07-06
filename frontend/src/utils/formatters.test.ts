import { describe, expect, it } from "vitest";
import {
  formatCurrency,
  formatDate,
  formatDistanceKm,
  formatFileSize,
  formatMm,
  formatNumber,
  formatPercent,
  formatRiskScore,
} from "./formatters";

describe("formatters", () => {
  it("formats currency in AUD with no decimals", () => {
    const formatted = formatCurrency(1_234_567);
    expect(formatted).toContain("1,234,567");
    expect(formatted.toLowerCase()).toMatch(/[$a]/);
  });

  it("returns em-dash for null currency", () => {
    expect(formatCurrency(null)).toBe("-");
  });

  it("formats whole and fractional numbers", () => {
    expect(formatNumber(42)).toBe("42");
    expect(formatNumber(3.14159, 2)).toBe("3.14");
    expect(formatNumber(null)).toBe("-");
  });

  it("formats percentages", () => {
    expect(formatPercent(0.123)).toBe("12.3%");
    expect(formatPercent(null)).toBe("-");
  });

  it("formats dates from ISO strings", () => {
    expect(formatDate("2025-12-31")).toMatch(/2025/);
    expect(formatDate(null)).toBe("-");
  });

  it("formats millimetres and kilometres", () => {
    expect(formatMm(215.5)).toBe("215.5 mm");
    expect(formatDistanceKm(4.2)).toBe("4.2 km");
    expect(formatMm(null)).toBe("-");
    expect(formatDistanceKm(null)).toBe("-");
  });

  it("formats risk scores", () => {
    expect(formatRiskScore(82.5)).toBe("82.5");
    expect(formatRiskScore(null)).toBe("-");
  });

  it("formats file sizes", () => {
    expect(formatFileSize(512)).toBe("512 B");
    expect(formatFileSize(2048)).toBe("2.0 KB");
    expect(formatFileSize(2_500_000)).toMatch(/MB$/);
  });
});
