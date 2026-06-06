import { useEffect, useState } from "react";
import { useParams, Link } from "react-router-dom";
import { css } from "../../styled-system/css";
import { getCompany, getCompanyRatios } from "../api/client";
import type { CompanyDetail, PeriodRatios, RatioResult } from "../api/types";
import { formatRatioValue } from "../components/RatioCard";

// ---------------------------------------------------------------------------
// Panda css() utility classes
// ---------------------------------------------------------------------------

const centerSpinnerCls = css({
  display: "flex",
  justifyContent: "center",
  padding: "12",
});

const backBtnMtCls = css({ marginTop: "4" });

const pageHeaderRowCls = css({
  display: "flex",
  alignItems: "flex-start",
  justifyContent: "space-between",
  flexWrap: "wrap",
  gap: "4",
});

const cardMbCls = css({ marginBottom: "6" });

const ratiosSpinnerCls = css({
  display: "flex",
  justifyContent: "center",
  padding: "8",
});

// Trend table period header link — inherit colour, no underline
const periodLinkCls = css({ color: "[inherit]", textDecoration: "none" }); // escape: "inherit" is not a color token

// Ratio unit suffix in trend table cell
const ratioUnitCls = css({
  fontSize: "xs",
  color: "textMuted",
  marginLeft: "[2px]", // escape hatch: 0.5 is not in spacing tokens; 2px matches original
});

export default function CompanyDetailPage() {
  const { companyId } = useParams<{ companyId: string }>();
  const id = Number(companyId);

  const [company, setCompany] = useState<CompanyDetail | null>(null);
  const [ratioData, setRatioData] = useState<PeriodRatios[] | null>(null);
  const [loadingCompany, setLoadingCompany] = useState(true);
  const [loadingRatios, setLoadingRatios] = useState(true);
  const [companyError, setCompanyError] = useState<string | null>(null);

  useEffect(() => {
    setLoadingCompany(true);
    getCompany(id)
      .then((data) => {
        setCompany(data);
      })
      .catch((err: unknown) => {
        setCompanyError(err instanceof Error ? err.message : "Failed to load");
      })
      .finally(() => {
        setLoadingCompany(false);
      });

    setLoadingRatios(true);
    getCompanyRatios(id)
      .then((d) => {
        setRatioData(d.periods);
      })
      .catch(() => {
        setRatioData([]);
      })
      .finally(() => {
        setLoadingRatios(false);
      });
  }, [id]);

  if (loadingCompany) {
    return (
      <div className={centerSpinnerCls}>
        <span className="spinner spinner-lg" />
      </div>
    );
  }

  if (companyError !== null || company === null) {
    return (
      <div>
        <div className="alert alert-danger">
          {companyError ?? "Company not found"}
        </div>
        <Link to="/companies" className={`btn btn-secondary ${backBtnMtCls}`}>
          Back to companies
        </Link>
      </div>
    );
  }

  return (
    <div>
      {/* Header */}
      <div className={`page-header ${pageHeaderRowCls}`}>
        <div>
          <h1 className="page-title">{company.name}</h1>
          <p className="page-subtitle">
            {[
              company.ticker && `Ticker: ${company.ticker}`,
              company.currency && `Currency: ${company.currency}`,
            ]
              .filter(Boolean)
              .join(" · ")}
          </p>
        </div>
        <Link to="/companies" className="btn btn-secondary btn-sm">
          All companies
        </Link>
      </div>

      {/* Periods */}
      <div className={`card ${cardMbCls}`}>
        <div className="card-header">
          <span className="card-title">Periods</span>
          <span className="text-sm text-muted">
            {company.periods.length} periods
          </span>
        </div>
        <div className="card-body">
          {company.periods.length === 0 ? (
            <div className="text-muted text-sm">
              No periods yet. Upload a document associated with this company.
            </div>
          ) : (
            <div className="periods-list">
              {company.periods.map((p) => (
                <Link
                  key={p.id}
                  to={`/review/${String(p.id)}`}
                  className="period-chip"
                >
                  {[p.period_type, p.fiscal_year, p.fiscal_period_end]
                    .filter(Boolean)
                    .join(" · ") || `Period #${String(p.id)}`}
                </Link>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Ratio trend table */}
      <div className="card">
        <div className="card-header">
          <span className="card-title">Ratio Trends</span>
          <span className="text-xs text-muted">
            N/A cells indicate missing inputs — hover for details
          </span>
        </div>
        <div className="card-body">
          {loadingRatios && (
            <div className={ratiosSpinnerCls}>
              <span className="spinner spinner-lg" />
            </div>
          )}

          {!loadingRatios && (!ratioData || ratioData.length === 0) && (
            <div className="empty-state">
              <div className="empty-state-icon">&#x1F4CA;</div>
              <div className="empty-state-title">No ratio data</div>
              <p>
                Upload documents and complete review to generate ratio trends.
              </p>
            </div>
          )}

          {!loadingRatios && ratioData && ratioData.length > 0 && (
            <RatioTrendTable
              periods={ratioData}
              periodLinkCls={periodLinkCls}
              ratioUnitCls={ratioUnitCls}
            />
          )}
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Ratio trend table component
// ---------------------------------------------------------------------------

interface TrendTableProps {
  periods: PeriodRatios[];
  periodLinkCls: string;
  ratioUnitCls: string;
}

function periodLabel(p: PeriodRatios["period"]): string {
  return (
    [p.period_type, p.fiscal_year, p.fiscal_period_end]
      .filter(Boolean)
      .join(" ") || `Period #${String(p.id)}`
  );
}

function RatioTrendTable({
  periods,
  periodLinkCls: linkCls,
  ratioUnitCls: unitCls,
}: TrendTableProps) {
  // Collect all unique ratio keys across periods, preserving order of first appearance
  const allRatios = new Map<string, RatioResult>();
  for (const pr of periods) {
    for (const r of pr.results) {
      if (!allRatios.has(r.key)) allRatios.set(r.key, r);
    }
  }

  if (allRatios.size === 0) {
    return (
      <div className="text-muted text-sm">
        No ratios available across these periods.
      </div>
    );
  }

  // Group ratio keys by category
  const categoryGroups = new Map<string, string[]>();
  for (const [key, r] of allRatios.entries()) {
    let group = categoryGroups.get(r.category);
    if (!group) {
      group = [];
      categoryGroups.set(r.category, group);
    }
    group.push(key);
  }

  // Build a lookup: period_id -> key -> RatioResult
  const byPeriod = new Map<number, Map<string, RatioResult>>();
  for (const pr of periods) {
    const m = new Map<string, RatioResult>();
    for (const r of pr.results) m.set(r.key, r);
    byPeriod.set(pr.period.id, m);
  }

  const colCount = periods.length;

  return (
    <div className="trend-table-wrap">
      <table className="trend-table">
        <thead>
          <tr>
            <th className="ratio-name-col">Ratio</th>
            {periods.map((pr) => (
              <th key={pr.period.id} className={css({ textAlign: "right" })}>
                <Link
                  to={`/review/${String(pr.period.id)}`}
                  className={linkCls}
                  title="Open review for this period"
                >
                  {periodLabel(pr.period)}
                </Link>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {Array.from(categoryGroups.entries()).map(([category, keys]) => (
            <>
              {/* Category separator row */}
              <tr key={`cat-${category}`} className="category-row">
                <td colSpan={colCount + 1}>{category}</td>
              </tr>

              {keys.map((key) => {
                const meta = allRatios.get(key);
                if (!meta) return null;
                return (
                  <tr key={key}>
                    <td className="ratio-name-col">{meta.name}</td>
                    {periods.map((pr) => {
                      const r = byPeriod.get(pr.period.id)?.get(key);
                      if (r?.status !== "ok" || r.value == null) {
                        // Build a tooltip that explains missing inputs
                        const missingMsg =
                          (r?.missing_inputs.length ?? 0) > 0
                            ? `Missing: ${r?.missing_inputs.join(", ") ?? ""}`
                            : (r?.detail ?? "Not available");
                        return (
                          <td
                            key={pr.period.id}
                            className="trend-cell-na"
                            title={missingMsg}
                          >
                            N/A
                          </td>
                        );
                      }
                      return (
                        <td key={pr.period.id} className="trend-cell-ok">
                          {formatRatioValue(r.value, r.unit)}
                          {r.unit && <span className={unitCls}>{r.unit}</span>}
                        </td>
                      );
                    })}
                  </tr>
                );
              })}
            </>
          ))}
        </tbody>
      </table>
    </div>
  );
}
