/**
 * Accessibility smoke test using axe-core (the engine that powers @axe-core/react).
 *
 * We render each key component and run axe directly on `document.body`.
 * This catches WCAG 2.x violations at the component level — a lightweight
 * complement to eslint-plugin-jsx-a11y static analysis.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render } from "@testing-library/react";
import { waitFor } from "@testing-library/react";
import axe from "axe-core";

// Suppress rules that are environment-specific or require full-page context.
// - color-contrast: requires rendered paint (not jsdom)
// - region: components are rendered in isolation, not inside full page landmarks
const AXE_CONFIG: axe.RunOptions = {
  rules: {
    "color-contrast": { enabled: false },
    "color-contrast-enhanced": { enabled: false },
    region: { enabled: false },
  },
};

/**
 * Run axe against document.body and assert no violations.
 */
async function assertNoViolations() {
  const result = await axe.run(document.body, AXE_CONFIG);
  if (result.violations.length > 0) {
    const msgs = result.violations
      .map((v) => `${v.id}: ${v.description}`)
      .join("\n");
    throw new Error(`Axe found accessibility violations:\n${msgs}`);
  }
  expect(result.violations).toHaveLength(0);
}

// ---------------------------------------------------------------------------
// StatusBadge
// ---------------------------------------------------------------------------
import StatusBadge from "../components/StatusBadge";
import type { DocStatus, RatioStatus } from "../api/types";

describe("a11y: StatusBadge", () => {
  afterEach(() => {
    document.body.innerHTML = "";
  });

  const statuses: DocStatus[] = [
    "uploaded",
    "parsing",
    "extracting",
    "needs_review",
    "ready",
    "failed",
  ];

  it.each(statuses)("status=%s has no axe violations", async (status) => {
    render(<StatusBadge status={status} />);
    await assertNoViolations();
  });
});

// ---------------------------------------------------------------------------
// RatioCard
// ---------------------------------------------------------------------------
import RatioCard from "../components/RatioCard";

describe("a11y: RatioCard", () => {
  afterEach(() => {
    document.body.innerHTML = "";
  });

  const ratioStatuses: RatioStatus[] = ["ok", "unavailable", "undefined"];

  it.each(ratioStatuses)(
    "RatioCard status=%s has no axe violations",
    async (status) => {
      render(
        <RatioCard
          ratio={{
            key: "test",
            name: "Test Ratio",
            category: "Test",
            status,
            value: status === "ok" ? 1.5 : null,
            unit: "x",
            missing_inputs: status === "unavailable" ? ["revenue"] : [],
            detail: null,
          }}
        />,
      );
      await assertNoViolations();
    },
  );
});

// ---------------------------------------------------------------------------
// AccountingChecksPanel (with mocked API)
// ---------------------------------------------------------------------------
import AccountingChecksPanel from "../components/AccountingChecksPanel";
import * as client from "../api/client";

vi.mock("../api/client", () => ({
  getPeriodValidation: vi.fn(),
}));

beforeEach(() => {
  vi.clearAllMocks();
});

describe("a11y: AccountingChecksPanel", () => {
  afterEach(() => {
    document.body.innerHTML = "";
  });

  it("renders with no axe violations after load", async () => {
    const mockFn = vi.mocked(client.getPeriodValidation);
    mockFn.mockResolvedValue({
      period_id: 1,
      results: [
        {
          key: "bs_balance",
          name: "Balance Sheet",
          status: "ok",
          lhs: 100,
          rhs: 100,
          difference: 0,
          tolerance: 1,
          missing_inputs: [],
          detail: null,
        },
        {
          key: "gp",
          name: "Gross Profit",
          status: "mismatch",
          lhs: 50,
          rhs: 45,
          difference: 5,
          tolerance: 1,
          missing_inputs: [],
          detail: null,
        },
      ],
      summary: { ok: 1, mismatch: 1 },
    });

    render(<AccountingChecksPanel periodId={1} />);
    // Wait for the async data load
    await waitFor(() => {
      expect(document.querySelector(".identity-panel")).not.toBeNull();
    });
    await assertNoViolations();
  });
});
