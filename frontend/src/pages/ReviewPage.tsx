import { useEffect, useState, useCallback } from "react";
import { useParams, Link } from "react-router-dom";
import { css } from "../../styled-system/css";
import { getPeriod, patchPeriodItems, getPeriodRatios } from "../api/client";
import type { PeriodDetail, RatioReport } from "../api/types";
import StatementEditor from "../components/StatementEditor";
import RatioGrid from "../components/RatioGrid";
import AccountingChecksPanel from "../components/AccountingChecksPanel";

type Tab = "items" | "ratios" | "checks";

// ---------------------------------------------------------------------------
// Panda css() utility classes (defined once at module level)
// ---------------------------------------------------------------------------

const centerSpinnerCls = css({
  display: "flex",
  justifyContent: "center",
  padding: "12",
});

const pageHeaderRowCls = css({
  display: "flex",
  alignItems: "flex-start",
  justifyContent: "space-between",
  flexWrap: "wrap",
  gap: "4",
});

const headerBtnGroupCls = css({ display: "flex", gap: "2" });

const alertMbCls = css({ marginBottom: "4" });

const metaCardBodyCls = css({
  display: "grid",
  gridTemplateColumns: "[repeat(auto-fill, minmax(160px, 1fr))]", // escape hatch: no grid token
  gap: "4",
});

const metaLabelCls = css({
  fontSize: "xs",
  color: "textMuted",
  fontWeight: "semibold",
  textTransform: "uppercase",
  letterSpacing: "0.04em",
});

const metaValueCls = css({
  fontSize: "base",
  fontWeight: "semibold",
  marginTop: "[2px]", // escape hatch: 0.5 not in spacing tokens; 2px matches original
});

const tabBarCls = css({
  display: "flex",
  borderBottom: "1px solid token(colors.border)",
  marginBottom: "6",
  gap: "[0]", // escape hatch: 0 is not in spacing tokens
});

function tabBtnCls(active: boolean) {
  return css({
    paddingBlock: "3",
    paddingInline: "5",
    border: "[none]", // escape hatch: "none" is not a border token
    borderBottom: active
      ? "[2px solid token(colors.brand)]" // escape hatch: compound border value
      : "[2px solid transparent]", // escape hatch: compound border value
    background: "[none]", // escape hatch: "none" is not a background token
    cursor: "pointer",
    fontWeight: active ? "bold" : "normal",
    color: active ? "brand" : "textMuted",
    fontSize: "sm",
    transition: "[color 0.15s, border-color 0.15s]", // escape hatch: compound transition
  });
}

const ratiosCardMbCls = css({ marginBottom: "6" });

const ratiosBtnMtCls = css({ marginTop: "3" });

const ratiosSpinnerCls = css({
  display: "flex",
  justifyContent: "center",
  padding: "8",
});

export default function ReviewPage() {
  const { periodId } = useParams<{ periodId: string }>();
  const id = Number(periodId);

  const [period, setPeriod] = useState<PeriodDetail | null>(null);
  const [ratioReport, setRatioReport] = useState<RatioReport | null>(null);
  const [loadingPeriod, setLoadingPeriod] = useState(true);
  const [loadingRatios, setLoadingRatios] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [saveSuccess, setSaveSuccess] = useState(false);
  const [periodError, setPeriodError] = useState<string | null>(null);
  const [tab, setTab] = useState<Tab>("items");

  // Market inputs for valuation ratios
  const [marketPrice, setMarketPrice] = useState<string>("");
  const [sharesOut, setSharesOut] = useState<string>("");

  const loadPeriod = useCallback(async () => {
    setLoadingPeriod(true);
    setPeriodError(null);
    try {
      const data = await getPeriod(id);
      setPeriod(data);
    } catch (err: unknown) {
      setPeriodError(
        err instanceof Error ? err.message : "Failed to load period",
      );
    } finally {
      setLoadingPeriod(false);
    }
  }, [id]);

  const loadRatios = useCallback(async () => {
    setLoadingRatios(true);
    try {
      const mp = parseFloat(marketPrice);
      const so = parseFloat(sharesOut);
      const ratioParams: import("../api/client").RatioParams = {};
      if (!isNaN(mp)) ratioParams.market_price = mp;
      if (!isNaN(so)) ratioParams.shares_outstanding = so;
      const report = await getPeriodRatios(id, ratioParams);
      setRatioReport(report);
    } catch {
      // ratio errors shown via empty state, not a blocking error
    } finally {
      setLoadingRatios(false);
    }
  }, [id, marketPrice, sharesOut]);

  useEffect(() => {
    void loadPeriod();
  }, [loadPeriod]);

  // Load ratios when switching to ratios tab or when period changes
  useEffect(() => {
    if (tab === "ratios") void loadRatios();
  }, [tab, loadRatios]);

  const handleSave = useCallback(
    async (updates: Record<string, number | null>) => {
      setSaving(true);
      setSaveError(null);
      setSaveSuccess(false);
      try {
        const updated = await patchPeriodItems(id, updates);
        setPeriod(updated);
        setSaveSuccess(true);
        setTimeout(() => {
          setSaveSuccess(false);
        }, 3000);
        // Invalidate ratio cache so re-fetch happens on next tab switch
        setRatioReport(null);
      } catch (err: unknown) {
        setSaveError(err instanceof Error ? err.message : "Save failed");
      } finally {
        setSaving(false);
      }
    },
    [id],
  );

  if (loadingPeriod) {
    return (
      <div className={centerSpinnerCls}>
        <span className="spinner spinner-lg" />
      </div>
    );
  }

  if (periodError) {
    return (
      <div>
        <div className="alert alert-danger">{periodError}</div>
        <Link
          to="/documents"
          className={`btn btn-secondary ${css({ marginTop: "4" })}`}
        >
          Back to documents
        </Link>
      </div>
    );
  }

  if (!period) return null;

  const periodLabel = [
    period.company_name,
    period.period_type,
    period.fiscal_year,
    period.fiscal_period_end,
  ]
    .filter(Boolean)
    .join(" · ");

  return (
    <div>
      {/* Header */}
      <div className={`page-header ${pageHeaderRowCls}`}>
        <div>
          <h1 className="page-title">Review Period</h1>
          <p className="page-subtitle">
            {periodLabel || `Period #${String(period.id)}`}
          </p>
        </div>
        <div className={headerBtnGroupCls}>
          {period.company_id && (
            <Link
              to={`/companies/${String(period.company_id)}`}
              className="btn btn-secondary btn-sm"
            >
              View company
            </Link>
          )}
          <Link to="/documents" className="btn btn-secondary btn-sm">
            All documents
          </Link>
        </div>
      </div>

      {/* Save feedback */}
      {saveSuccess && (
        <div className={`alert alert-success ${alertMbCls}`}>
          Changes saved successfully.
        </div>
      )}
      {saveError && (
        <div className={`alert alert-danger ${alertMbCls}`}>{saveError}</div>
      )}

      {/* Period meta */}
      <div className={`card ${css({ marginBottom: "6" })}`}>
        <div className="card-body">
          <div className={metaCardBodyCls}>
            {[
              ["Company", period.company_name ?? "—"],
              ["Period type", period.period_type ?? "—"],
              ["Fiscal year", period.fiscal_year ?? "—"],
              ["Period end", period.fiscal_period_end ?? "—"],
              ["Currency", period.currency ?? "—"],
            ].map(([label, value]) => (
              <div key={String(label)}>
                <div className={metaLabelCls}>{label}</div>
                <div className={metaValueCls}>{value}</div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Tabs */}
      <div className={tabBarCls}>
        {(["items", "ratios", "checks"] as Tab[]).map((t) => (
          <button
            key={t}
            onClick={() => {
              setTab(t);
            }}
            className={tabBtnCls(tab === t)}
          >
            {t === "items"
              ? "Extracted Items"
              : t === "ratios"
                ? "Ratio Report"
                : "Accounting Checks"}
          </button>
        ))}
      </div>

      {/* Tab content */}
      {tab === "items" && (
        <div className="card">
          <div className="card-header">
            <span className="card-title">Extracted Line Items</span>
            <span className="text-sm text-muted">
              {Object.keys(period.items).length} items extracted
            </span>
          </div>
          <div className="card-body">
            <StatementEditor
              period={period}
              onSave={handleSave}
              saving={saving}
            />
          </div>
        </div>
      )}

      {tab === "ratios" && (
        <div>
          {/* Optional market params for valuation ratios */}
          <div className={`card ${ratiosCardMbCls}`}>
            <div className="card-header">
              <span className="card-title">Valuation Inputs (optional)</span>
              <span className="text-xs text-muted">
                Required for P/E, P/B, EV/EBITDA, etc.
              </span>
            </div>
            <div className="card-body">
              <div className="form-row">
                <div className="form-group">
                  <label className="form-label" htmlFor="market-price">
                    Market price per share
                  </label>
                  <input
                    id="market-price"
                    type="number"
                    step="any"
                    className="form-input"
                    value={marketPrice}
                    placeholder="e.g. 142.50"
                    onChange={(e) => {
                      setMarketPrice(e.target.value);
                    }}
                  />
                </div>
                <div className="form-group">
                  <label className="form-label" htmlFor="shares-out">
                    Shares outstanding
                  </label>
                  <input
                    id="shares-out"
                    type="number"
                    step="any"
                    className="form-input"
                    value={sharesOut}
                    placeholder="e.g. 1000000000"
                    onChange={(e) => {
                      setSharesOut(e.target.value);
                    }}
                  />
                </div>
              </div>
              <div className={ratiosBtnMtCls}>
                <button
                  className="btn btn-primary btn-sm"
                  onClick={loadRatios}
                  disabled={loadingRatios}
                >
                  {loadingRatios ? <span className="spinner" /> : null}
                  Compute ratios
                </button>
              </div>
            </div>
          </div>

          {loadingRatios && (
            <div className={ratiosSpinnerCls}>
              <span className="spinner spinner-lg" />
            </div>
          )}

          {!loadingRatios && ratioReport && (
            <RatioGrid results={ratioReport.results} />
          )}

          {!loadingRatios && !ratioReport && (
            <div className="empty-state card">
              <div className="empty-state-icon">&#x1F4CA;</div>
              <div className="empty-state-title">No ratio data</div>
              <p>Click "Compute ratios" above to generate the ratio report.</p>
            </div>
          )}
        </div>
      )}

      {tab === "checks" && (
        <div className="card">
          <div className="card-header">
            <span className="card-title">Accounting Checks</span>
            <span className="text-xs text-muted">
              Deterministic identity validation — not LLM-generated
            </span>
          </div>
          <div className="card-body">
            <AccountingChecksPanel periodId={id} />
          </div>
        </div>
      )}
    </div>
  );
}
