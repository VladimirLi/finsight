import { describe, it, expect } from "vitest";
import { formatRatioValue } from "../components/RatioCard";

describe("formatRatioValue", () => {
  it("formats percentages to 1 decimal place", () => {
    expect(formatRatioValue(42.567, "%")).toBe("42.6");
    expect(formatRatioValue(100, "%")).toBe("100.0");
  });

  it("formats multiplier ratios to 2 decimal places", () => {
    expect(formatRatioValue(2.3456, "x")).toBe("2.35");
    expect(formatRatioValue(1, "x")).toBe("1.00");
  });

  it("formats values >= 1,000,000 in millions", () => {
    expect(formatRatioValue(5_000_000, "USD")).toBe("5.00M");
    expect(formatRatioValue(1_500_000, "USD")).toBe("1.50M");
  });

  it("formats values >= 1,000 in thousands", () => {
    expect(formatRatioValue(2_500, "USD")).toBe("2.5K");
    expect(formatRatioValue(1_000, "USD")).toBe("1.0K");
  });

  it("formats plain ratios to 2 decimal places", () => {
    expect(formatRatioValue(3.14159, "days")).toBe("3.14");
    expect(formatRatioValue(0.5, "")).toBe("0.50");
  });

  it("handles negative values in millions", () => {
    expect(formatRatioValue(-2_000_000, "USD")).toBe("-2.00M");
  });
});
