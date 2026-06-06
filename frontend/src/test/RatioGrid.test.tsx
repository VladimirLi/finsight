import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import RatioGrid from "../components/RatioGrid";
import type { RatioResult } from "../api/types";

const makeRatio = (
  overrides: Partial<RatioResult> & Pick<RatioResult, "key" | "name">,
): RatioResult => ({
  category: "Liquidity",
  status: "ok",
  value: 1.5,
  unit: "x",
  missing_inputs: [],
  detail: null,
  ...overrides,
});

describe("RatioGrid — empty state", () => {
  it("shows an empty-state message when results array is empty", () => {
    render(<RatioGrid results={[]} />);
    expect(screen.getByText("No ratios computed")).toBeInTheDocument();
  });
});

describe("RatioGrid — with results", () => {
  const results: RatioResult[] = [
    makeRatio({
      key: "current_ratio",
      name: "Current Ratio",
      category: "Liquidity",
    }),
    makeRatio({
      key: "quick_ratio",
      name: "Quick Ratio",
      category: "Liquidity",
      value: 0.9,
    }),
    makeRatio({
      key: "gross_margin",
      name: "Gross Margin",
      category: "Profitability",
      value: 35.0,
      unit: "%",
    }),
  ];

  it("renders a section for each unique category", () => {
    render(<RatioGrid results={results} />);
    expect(screen.getByText("Liquidity")).toBeInTheDocument();
    expect(screen.getByText("Profitability")).toBeInTheDocument();
  });

  it("renders each ratio name", () => {
    render(<RatioGrid results={results} />);
    expect(screen.getByText("Current Ratio")).toBeInTheDocument();
    expect(screen.getByText("Quick Ratio")).toBeInTheDocument();
    expect(screen.getByText("Gross Margin")).toBeInTheDocument();
  });
});
