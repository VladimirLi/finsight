/**
 * Re-exports from generated openapi.d.ts types.
 * Source of truth: backend/openapi.json → generated via `npm run gen:api-types`.
 * Hand-written aliases live below the re-export block.
 */
import type { components } from "./openapi.d.ts";

// ── Schema aliases ──────────────────────────────────────────────────────────

/** Document pipeline status values. */
export type DocStatus =
  | "uploaded"
  | "parsing"
  | "extracting"
  | "needs_review"
  | "ready"
  | "failed";

/** A document list item (no period detail). */
export type DocumentT = Omit<components["schemas"]["DocumentOut"], "status"> & {
  status: DocStatus;
};

/** Single financial line item with provenance. */
export type FinancialValue = components["schemas"]["FinancialValueOut"];

/** Full period with all line items. */
export type PeriodDetail = components["schemas"]["PeriodDetailOut"];

/** Document with its associated period. */
export type DocumentDetail = Omit<
  components["schemas"]["DocumentDetailOut"],
  "status"
> & {
  status: DocStatus;
};

/** Lightweight company record. */
export type Company = components["schemas"]["CompanyOut"];

/** Company with its period list. */
export type CompanyDetail = components["schemas"]["CompanyDetailOut"];

/** Ratio computation status. */
export type RatioStatus = "ok" | "unavailable" | "undefined";

/** A single ratio result (status narrowed from string to RatioStatus union). */
export type RatioResult = Omit<
  components["schemas"]["RatioResultOut"],
  "status"
> & {
  status: RatioStatus;
};

/** Full ratio report for a period. */
export type RatioReport = Omit<
  components["schemas"]["RatioReportOut"],
  "results"
> & {
  results: RatioResult[];
};

/** One period + its ratios (used in company trend view). */
export type PeriodRatios = Omit<
  components["schemas"]["PeriodRatiosOut"],
  "results"
> & {
  results: RatioResult[];
};

// ── Validation / accounting identity types ─────────────────────────────────

/** Identity check status values. */
export type IdentityStatus = "ok" | "mismatch" | "unavailable";

/** A single accounting identity check result. */
export type IdentityResult = Omit<
  components["schemas"]["IdentityResultOut"],
  "status"
> & {
  status: IdentityStatus;
};

/** Full validation report for a period. */
export type ValidationReport = Omit<
  components["schemas"]["ValidationReportOut"],
  "results"
> & {
  results: IdentityResult[];
};
