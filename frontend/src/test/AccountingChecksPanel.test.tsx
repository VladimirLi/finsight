import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import AccountingChecksPanel from "../components/AccountingChecksPanel";
import * as client from "../api/client";
import type { ValidationReport } from "../api/types";

// ---------------------------------------------------------------------------
// Mock the API client
// ---------------------------------------------------------------------------
vi.mock("../api/client", () => ({
  getPeriodValidation: vi.fn(),
}));

const mockGetPeriodValidation = vi.mocked(client.getPeriodValidation);

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------
const okReport: ValidationReport = {
  period_id: 1,
  results: [
    {
      key: "bs_balance",
      name: "Balance Sheet: Assets = Liabilities + Equity",
      status: "ok",
      lhs: 100_000,
      rhs: 100_000,
      difference: 0,
      tolerance: 1,
      missing_inputs: [],
      detail: null,
    },
  ],
  summary: { ok: 1 },
};

const mismatchReport: ValidationReport = {
  period_id: 2,
  results: [
    {
      key: "bs_balance",
      name: "Balance Sheet: Assets = Liabilities + Equity",
      status: "mismatch",
      lhs: 105_000,
      rhs: 100_000,
      difference: 5_000,
      tolerance: 1,
      missing_inputs: [],
      detail: "Difference exceeds tolerance",
    },
  ],
  summary: { mismatch: 1 },
};

const unavailableReport: ValidationReport = {
  period_id: 3,
  results: [
    {
      key: "bs_balance",
      name: "Balance Sheet: Assets = Liabilities + Equity",
      status: "unavailable",
      lhs: null,
      rhs: null,
      difference: null,
      tolerance: null,
      missing_inputs: ["total_assets", "total_liabilities"],
      detail: null,
    },
  ],
  summary: { unavailable: 1 },
};

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------
beforeEach(() => {
  vi.clearAllMocks();
});

describe("AccountingChecksPanel — loading state", () => {
  it("shows a spinner while loading", () => {
    // Never resolves during this test
    mockGetPeriodValidation.mockReturnValue(new Promise(() => undefined));
    render(<AccountingChecksPanel periodId={1} />);
    expect(
      screen.getByLabelText("Loading accounting checks"),
    ).toBeInTheDocument();
  });
});

describe("AccountingChecksPanel — ok result", () => {
  it("renders OK badge and summary chip", async () => {
    mockGetPeriodValidation.mockResolvedValue(okReport);
    render(<AccountingChecksPanel periodId={1} />);
    await waitFor(() => {
      expect(screen.getByText("OK")).toBeInTheDocument();
    });
    // Summary chip
    expect(screen.getByText(/ok.*1/i)).toBeInTheDocument();
  });

  it("renders the identity name", async () => {
    mockGetPeriodValidation.mockResolvedValue(okReport);
    render(<AccountingChecksPanel periodId={1} />);
    await waitFor(() => {
      expect(
        screen.getByText("Balance Sheet: Assets = Liabilities + Equity"),
      ).toBeInTheDocument();
    });
  });
});

describe("AccountingChecksPanel — mismatch result", () => {
  it("shows Mismatch badge", async () => {
    mockGetPeriodValidation.mockResolvedValue(mismatchReport);
    render(<AccountingChecksPanel periodId={2} />);
    await waitFor(() => {
      expect(screen.getByText("Mismatch")).toBeInTheDocument();
    });
  });

  it("shows LHS and RHS values", async () => {
    mockGetPeriodValidation.mockResolvedValue(mismatchReport);
    render(<AccountingChecksPanel periodId={2} />);
    await waitFor(() => {
      expect(screen.getByText(/LHS/)).toBeInTheDocument();
      expect(screen.getByText(/RHS/)).toBeInTheDocument();
    });
  });

  it("shows the difference (Δ prefix)", async () => {
    mockGetPeriodValidation.mockResolvedValue(mismatchReport);
    render(<AccountingChecksPanel periodId={2} />);
    await waitFor(() => {
      // The difference row contains "Δ" prefix
      expect(screen.getByText(/Δ/)).toBeInTheDocument();
    });
  });
});

describe("AccountingChecksPanel — unavailable result", () => {
  it("shows Unavailable badge", async () => {
    mockGetPeriodValidation.mockResolvedValue(unavailableReport);
    render(<AccountingChecksPanel periodId={3} />);
    await waitFor(() => {
      expect(screen.getByText("Unavailable")).toBeInTheDocument();
    });
  });

  it("lists missing inputs", async () => {
    mockGetPeriodValidation.mockResolvedValue(unavailableReport);
    render(<AccountingChecksPanel periodId={3} />);
    await waitFor(() => {
      expect(
        screen.getByText(/total_assets, total_liabilities/),
      ).toBeInTheDocument();
    });
  });
});

describe("AccountingChecksPanel — error state", () => {
  it("shows an error alert on API failure", async () => {
    mockGetPeriodValidation.mockRejectedValue(new Error("Network error"));
    render(<AccountingChecksPanel periodId={1} />);
    await waitFor(() => {
      expect(screen.getByRole("alert")).toBeInTheDocument();
      expect(screen.getByText("Network error")).toBeInTheDocument();
    });
  });
});

describe("AccountingChecksPanel — empty state", () => {
  it("shows empty state when no results", async () => {
    mockGetPeriodValidation.mockResolvedValue({
      period_id: 1,
      results: [],
      summary: {},
    });
    render(<AccountingChecksPanel periodId={1} />);
    await waitFor(() => {
      expect(screen.getByText("No checks available")).toBeInTheDocument();
    });
  });
});
