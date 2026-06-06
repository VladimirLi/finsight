import { useState, useCallback } from "react";
import { css } from "../../styled-system/css";
import type { PeriodDetail, FinancialValue } from "../api/types";

// ---------------------------------------------------------------------------
// Canonical field groups (mirrors backend/app/schemas/financials.py)
// ---------------------------------------------------------------------------
const INCOME_FIELDS = [
  "revenue",
  "cost_of_goods_sold",
  "gross_profit",
  "operating_expenses",
  "research_and_development",
  "selling_general_admin",
  "depreciation_amortization",
  "operating_income",
  "interest_expense",
  "interest_income",
  "pretax_income",
  "income_tax_expense",
  "net_income",
  "ebitda",
  "shares_outstanding_diluted",
  "shares_outstanding_basic",
  "eps_diluted",
];

const BALANCE_FIELDS = [
  "cash_and_equivalents",
  "short_term_investments",
  "accounts_receivable",
  "inventory",
  "prepaid_expenses",
  "other_current_assets",
  "total_current_assets",
  "property_plant_equipment_net",
  "goodwill",
  "intangible_assets",
  "long_term_investments",
  "other_non_current_assets",
  "total_non_current_assets",
  "total_assets",
  "accounts_payable",
  "short_term_debt",
  "accrued_liabilities",
  "deferred_revenue_current",
  "other_current_liabilities",
  "total_current_liabilities",
  "long_term_debt",
  "deferred_tax_liabilities",
  "other_non_current_liabilities",
  "total_non_current_liabilities",
  "total_liabilities",
  "common_stock",
  "retained_earnings",
  "treasury_stock",
  "total_equity",
  "minority_interest",
];

const CASH_FLOW_FIELDS = [
  "operating_cash_flow",
  "depreciation_amortization_cf",
  "stock_based_compensation",
  "change_in_working_capital",
  "capital_expenditures",
  "acquisitions",
  "investing_cash_flow",
  "debt_issued",
  "debt_repaid",
  "dividends_paid",
  "share_repurchases",
  "financing_cash_flow",
  "free_cash_flow",
  "net_change_in_cash",
];

const SECTIONS: { label: string; fields: string[] }[] = [
  { label: "Income Statement", fields: INCOME_FIELDS },
  { label: "Balance Sheet", fields: BALANCE_FIELDS },
  { label: "Cash Flow Statement", fields: CASH_FLOW_FIELDS },
];

const LOW_CONFIDENCE_THRESHOLD = 0.7;

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------
function humanizeKey(key: string): string {
  return key.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

// Panda css() classes for the header row labels
const headerRowCls = css({
  fontWeight: "semibold",
  fontSize: "xs",
  color: "textMuted",
});

// "not extracted" italic label
const notExtractedCls = css({
  color: "textSubtle",
  fontStyle: "italic",
});

// Source page center wrapper
const pageCenterCls = css({ textAlign: "center" });

// Dash placeholder for missing page
const pageDashCls = css({ color: "textSubtle" });

// Flags cell
const flagsCellCls = css({
  display: "flex",
  gap: "1",
  flexWrap: "wrap",
  justifyContent: "flex-end",
});

// Low-confidence inline badge (overrides the generic .badge text-transform/spacing)
const lowConfBadgeCls = css({
  background: "unavailableBg",
  color: "unavailable",
  textTransform: "none",
  letterSpacing: "[0]", // escape hatch: 0 is not in spacing tokens
});

// Sticky save bar
const saveBarCls = css({
  position: "sticky",
  bottom: "[0]", // escape hatch: 0 is not in spacing tokens
  background: "surface",
  borderTop: "1px solid token(colors.border)",
  padding: "4",
  display: "flex",
  alignItems: "center",
  justifyContent: "flex-end",
  gap: "3",
  marginTop: "4",
});

// Edited count label inside save bar
const editCountCls = css({ fontSize: "sm", color: "textMuted" });

function ConfidenceBar({ confidence }: { confidence: number | null }) {
  if (confidence == null) return <span className="text-muted text-xs">—</span>;
  const pct = Math.round(confidence * 100);
  const cls = confidence >= 0.85 ? "" : confidence >= 0.6 ? "medium" : "low";
  return (
    <div className="confidence-bar">
      <div className="confidence-track">
        <div
          className={`confidence-fill ${cls}`}
          // eslint-disable-next-line no-restricted-syntax
          style={{ width: `${String(pct)}%` }} // escape hatch: dynamic runtime % cannot be a static token
        />
      </div>
      <span className="confidence-pct">{pct}%</span>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Props / component
// ---------------------------------------------------------------------------
interface Props {
  period: PeriodDetail;
  onSave: (updates: Record<string, number | null>) => Promise<void>;
  saving: boolean;
}

/**
 * Editable table of all canonical financial line items, grouped by statement
 * section. Highlights low-confidence and user-edited values. Collects edits
 * locally and calls onSave with the delta when the user clicks Save.
 */
export default function StatementEditor({ period, onSave, saving }: Props) {
  // Local overrides: key -> string input (so we can handle "" and invalid)
  const [edits, setEdits] = useState<Record<string, string>>({});

  const handleChange = useCallback((key: string, raw: string) => {
    setEdits((prev) => ({ ...prev, [key]: raw }));
  }, []);

  const handleSave = useCallback(async () => {
    const updates: Record<string, number | null> = {};
    for (const [key, raw] of Object.entries(edits)) {
      const trimmed = raw.trim();
      if (trimmed === "" || trimmed.toLowerCase() === "null") {
        updates[key] = null;
      } else {
        const n = parseFloat(trimmed);
        if (!isNaN(n)) updates[key] = n;
        // If still NaN we skip; user hasn't entered a valid number
      }
    }
    if (Object.keys(updates).length === 0) return;
    await onSave(updates);
    setEdits({});
  }, [edits, onSave]);

  const hasEdits = Object.keys(edits).length > 0;

  return (
    <div>
      {/* Header row labels */}
      <div className={`item-row ${headerRowCls}`}>
        <span>Field</span>
        <span>Source label</span>
        <span className={css({ textAlign: "right" })}>Value</span>
        <span>Confidence</span>
        <span className={css({ textAlign: "center" })}>Page</span>
        <span />
      </div>

      {SECTIONS.map(({ label, fields }) => {
        // Show all canonical fields so users know what's missing
        const allFields = fields;

        return (
          <div key={label} className="section-group">
            <div className="section-group-title">{label}</div>
            {allFields.map((key) => {
              const fv: FinancialValue | undefined = period.items[key];
              const localValue = edits[key];
              const hasLocal = localValue !== undefined;

              const displayValue = hasLocal
                ? localValue
                : fv?.value != null
                  ? String(fv.value)
                  : "";

              const isLowConf =
                fv?.confidence != null &&
                fv.confidence < LOW_CONFIDENCE_THRESHOLD;
              const isEdited = fv?.edited_by_user ?? false;
              const isLocalEdited = hasLocal;

              let rowCls = "item-row";
              if (isLocalEdited || isEdited) rowCls += " user-edited";
              else if (isLowConf) rowCls += " low-confidence";

              return (
                <div key={key} className={rowCls}>
                  {/* Field key */}
                  <span className="item-key">{key}</span>

                  {/* Source label from document */}
                  <span className="item-label" title={fv?.source_label ?? ""}>
                    {fv?.source_label ?? (
                      <span className={notExtractedCls}>not extracted</span>
                    )}
                  </span>

                  {/* Editable value */}
                  <input
                    type="text"
                    inputMode="numeric"
                    className={`item-input${isLocalEdited ? " edited" : ""}`}
                    value={displayValue}
                    placeholder="null"
                    onChange={(e) => {
                      handleChange(key, e.target.value);
                    }}
                    aria-label={humanizeKey(key)}
                  />

                  {/* Confidence bar */}
                  <ConfidenceBar confidence={fv?.confidence ?? null} />

                  {/* Source page chip */}
                  <span className={pageCenterCls}>
                    {fv?.source_page != null ? (
                      <span className="page-chip">p.{fv.source_page}</span>
                    ) : (
                      <span className={pageDashCls}>—</span>
                    )}
                  </span>

                  {/* Flags */}
                  <span className={flagsCellCls}>
                    {isEdited && !isLocalEdited && (
                      <span className="tag-edited">edited</span>
                    )}
                    {isLowConf && !isLocalEdited && (
                      <span
                        className={`badge ${lowConfBadgeCls}`}
                        title="Low confidence extraction"
                      >
                        low conf
                      </span>
                    )}
                  </span>
                </div>
              );
            })}
          </div>
        );
      })}

      {/* Save bar */}
      <div className={saveBarCls}>
        {hasEdits && (
          <span className={editCountCls}>
            {Object.keys(edits).length} field
            {Object.keys(edits).length !== 1 ? "s" : ""} edited
          </span>
        )}
        <button
          className="btn btn-secondary btn-sm"
          disabled={!hasEdits || saving}
          onClick={() => {
            setEdits({});
          }}
        >
          Discard
        </button>
        <button
          className="btn btn-primary"
          disabled={!hasEdits || saving}
          onClick={handleSave}
        >
          {saving ? <span className="spinner" /> : null}
          Save changes
        </button>
      </div>
    </div>
  );
}
