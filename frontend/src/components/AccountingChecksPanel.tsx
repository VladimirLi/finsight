import { useEffect, useState } from "react";
import { getPeriodValidation } from "../api/client";
import type {
  IdentityResult,
  IdentityStatus,
  ValidationReport,
} from "../api/types";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface Props {
  periodId: number;
}

// ---------------------------------------------------------------------------
// Status badge labels / colours (mirror the ratio-card pattern)
// ---------------------------------------------------------------------------

const STATUS_LABEL: Record<IdentityStatus, string> = {
  ok: "OK",
  mismatch: "Mismatch",
  unavailable: "Unavailable",
};

const STATUS_CLASS: Record<IdentityStatus, string> = {
  ok: "badge-identity-ok",
  mismatch: "badge-identity-mismatch",
  unavailable: "badge-identity-unavailable",
};

function IdentityBadge({ status }: { status: IdentityStatus }) {
  return (
    <span className={`badge-identity ${STATUS_CLASS[status]}`}>
      {STATUS_LABEL[status]}
    </span>
  );
}

// ---------------------------------------------------------------------------
// Row for a single identity check
// ---------------------------------------------------------------------------

function IdentityRow({ result }: { result: IdentityResult }) {
  return (
    <div className={`identity-row identity-row--${result.status}`}>
      {/* Name + badge */}
      <div className="identity-row__name">
        <span className="identity-row__label">{result.name}</span>
        <IdentityBadge status={result.status} />
      </div>

      {/* Mismatch detail: show lhs vs rhs + difference */}
      {result.status === "mismatch" && (
        <div className="identity-row__detail">
          <span className="identity-row__lhs">
            LHS: {result.lhs?.toLocaleString() ?? "—"}
          </span>
          <span className="identity-row__sep">≠</span>
          <span className="identity-row__rhs">
            RHS: {result.rhs?.toLocaleString() ?? "—"}
          </span>
          {result.difference != null && (
            <span className="identity-row__diff">
              Δ {result.difference.toLocaleString()}
            </span>
          )}
        </div>
      )}

      {/* Unavailable: list missing inputs */}
      {result.status === "unavailable" && result.missing_inputs.length > 0 && (
        <div className="identity-row__missing">
          Missing: {result.missing_inputs.join(", ")}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Summary chips
// ---------------------------------------------------------------------------

function SummaryChips({ summary }: { summary: ValidationReport["summary"] }) {
  const pairs = Object.entries(summary) as [IdentityStatus, number][];
  if (pairs.length === 0) return null;

  const CHIP_CLASS: Record<IdentityStatus, string> = {
    ok: "summary-chip--ok",
    mismatch: "summary-chip--mismatch",
    unavailable: "summary-chip--unavailable",
  };

  return (
    <div className="identity-summary">
      {pairs.map(([status, count]) => (
        <span key={status} className={`summary-chip ${CHIP_CLASS[status]}`}>
          {STATUS_LABEL[status]}: {count}
        </span>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main panel
// ---------------------------------------------------------------------------

/**
 * Fetches and displays accounting identity checks for a single period.
 * Shows OK / mismatch / unavailable badges per identity, and for mismatches
 * exposes LHS vs RHS + difference to help diagnose extraction errors.
 */
export default function AccountingChecksPanel({ periodId }: Props) {
  const [report, setReport] = useState<ValidationReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    setError(null);
    getPeriodValidation(periodId)
      .then((data) => {
        setReport(data);
      })
      .catch((err: unknown) => {
        setError(err instanceof Error ? err.message : "Failed to load checks");
      })
      .finally(() => {
        setLoading(false);
      });
  }, [periodId]);

  if (loading) {
    return (
      <div className="identity-panel-loading">
        <span className="spinner" aria-label="Loading accounting checks" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="alert alert-danger" role="alert">
        {error}
      </div>
    );
  }

  if (!report || report.results.length === 0) {
    return (
      <div className="empty-state">
        <div className="empty-state-title">No checks available</div>
        <p>Accounting identities will appear once line items are extracted.</p>
      </div>
    );
  }

  return (
    <section aria-label="Accounting checks" className="identity-panel">
      <SummaryChips summary={report.summary} />
      <div className="identity-list">
        {report.results.map((r) => (
          <IdentityRow key={r.key} result={r} />
        ))}
      </div>
    </section>
  );
}
