import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import RatioCard from "../components/RatioCard";
import type { RatioResult } from "../api/types";

const okRatio: RatioResult = {
  key: "current_ratio",
  name: "Current Ratio",
  category: "Liquidity",
  status: "ok",
  value: 2.35,
  unit: "x",
  missing_inputs: [],
  detail: null,
};

const unavailableRatio: RatioResult = {
  key: "debt_to_equity",
  name: "Debt / Equity",
  category: "Leverage",
  status: "unavailable",
  value: null,
  unit: "x",
  missing_inputs: ["total_equity", "total_debt"],
  detail: null,
};

const percentRatio: RatioResult = {
  key: "gross_margin",
  name: "Gross Margin",
  category: "Profitability",
  status: "ok",
  value: 42.5,
  unit: "%",
  missing_inputs: [],
  detail: "Based on reported figures",
};

describe("RatioCard — ok status", () => {
  it("renders the ratio name", () => {
    render(<RatioCard ratio={okRatio} />);
    expect(screen.getByText("Current Ratio")).toBeInTheDocument();
  });

  it("renders the formatted value with unit for a multiplier ratio", () => {
    render(<RatioCard ratio={okRatio} />);
    // value 2.35 formatted as "2.35" with unit "x"
    expect(screen.getByText("2.35")).toBeInTheDocument();
    expect(screen.getByText("x")).toBeInTheDocument();
  });

  it("renders a percentage value with 1 decimal place", () => {
    render(<RatioCard ratio={percentRatio} />);
    expect(screen.getByText("42.5")).toBeInTheDocument();
    expect(screen.getByText("%")).toBeInTheDocument();
  });

  it("renders the detail text when present", () => {
    render(<RatioCard ratio={percentRatio} />);
    expect(screen.getByText("Based on reported figures")).toBeInTheDocument();
  });
});

describe("RatioCard — unavailable status", () => {
  it("renders N/A when status is unavailable", () => {
    render(<RatioCard ratio={unavailableRatio} />);
    expect(screen.getByText("N/A")).toBeInTheDocument();
  });

  it("lists the missing inputs", () => {
    render(<RatioCard ratio={unavailableRatio} />);
    expect(
      screen.getByText("Missing: total_equity, total_debt"),
    ).toBeInTheDocument();
  });

  it("does not render a numeric value", () => {
    render(<RatioCard ratio={unavailableRatio} />);
    expect(screen.queryByText(/^\d+\.\d+/)).not.toBeInTheDocument();
  });
});
