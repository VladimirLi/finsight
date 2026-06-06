import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { css } from "../../styled-system/css";
import { listCompanies, createCompany } from "../api/client";
import type { Company } from "../api/types";

interface CreateForm {
  name: string;
  ticker: string;
  currency: string;
}

const DEFAULT_FORM: CreateForm = { name: "", ticker: "", currency: "USD" };

// ---------------------------------------------------------------------------
// Panda css() utility classes
// ---------------------------------------------------------------------------

const pageHeaderRowCls = css({
  display: "flex",
  alignItems: "center",
  justifyContent: "space-between",
});

const centerSpinnerCls = css({
  display: "flex",
  justifyContent: "center",
  padding: "12",
});

const emptyStateBtnMtCls = css({ marginTop: "4" });

const modalFormBodyCls = css({
  display: "flex",
  flexDirection: "column",
  gap: "4",
});

const modalActionRowCls = css({
  display: "flex",
  justifyContent: "flex-end",
  gap: "3",
});

export default function CompaniesPage() {
  const [companies, setCompanies] = useState<Company[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [showModal, setShowModal] = useState(false);
  const [form, setForm] = useState<CreateForm>(DEFAULT_FORM);
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await listCompanies();
      setCompanies(data.slice().sort((a, b) => a.name.localeCompare(b.name)));
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to load companies");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
  }, []);

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!form.name.trim()) return;
    setCreating(true);
    setCreateError(null);
    try {
      const trimmedTicker = form.ticker.trim();
      const trimmedCurrency = form.currency.trim();
      const created = await createCompany({
        name: form.name.trim(),
        ...(trimmedTicker ? { ticker: trimmedTicker } : {}),
        ...(trimmedCurrency ? { currency: trimmedCurrency } : {}),
      });
      setCompanies((prev) =>
        [...prev, created].sort((a, b) => a.name.localeCompare(b.name)),
      );
      setShowModal(false);
      setForm(DEFAULT_FORM);
    } catch (err: unknown) {
      setCreateError(err instanceof Error ? err.message : "Create failed");
    } finally {
      setCreating(false);
    }
  };

  return (
    <div>
      <div className={`page-header ${pageHeaderRowCls}`}>
        <div>
          <h1 className="page-title">Companies</h1>
          <p className="page-subtitle">
            Manage companies and compare period ratios
          </p>
        </div>
        <button
          className="btn btn-primary"
          onClick={() => {
            setShowModal(true);
          }}
        >
          + New company
        </button>
      </div>

      {error && <div className="alert alert-danger">{error}</div>}

      {loading && (
        <div className={centerSpinnerCls}>
          <span className="spinner spinner-lg" />
        </div>
      )}

      {!loading && companies.length === 0 && !error && (
        <div className="empty-state card">
          <div className="empty-state-icon">&#x1F3E2;</div>
          <div className="empty-state-title">No companies yet</div>
          <p>Create a company to group documents by entity.</p>
          <div className={emptyStateBtnMtCls}>
            <button
              className="btn btn-primary"
              onClick={() => {
                setShowModal(true);
              }}
            >
              Create company
            </button>
          </div>
        </div>
      )}

      {!loading && companies.length > 0 && (
        <div className="company-grid">
          {companies.map((c) => (
            <Link
              key={c.id}
              to={`/companies/${String(c.id)}`}
              className="company-card"
            >
              <div className="company-name">{c.name}</div>
              <div className="company-meta">
                {[
                  c.ticker && `Ticker: ${c.ticker}`,
                  c.currency && `Currency: ${c.currency}`,
                ]
                  .filter(Boolean)
                  .join(" · ") || "No metadata"}
              </div>
            </Link>
          ))}
        </div>
      )}

      {/* Create modal */}
      {showModal && (
        <div
          className="modal-backdrop"
          role="presentation"
          onClick={(e) => {
            if (e.target === e.currentTarget) {
              setShowModal(false);
              setForm(DEFAULT_FORM);
              setCreateError(null);
            }
          }}
          onKeyDown={(e) => {
            if (e.key === "Escape") {
              setShowModal(false);
              setForm(DEFAULT_FORM);
              setCreateError(null);
            }
          }}
        >
          <form className="modal" onSubmit={handleCreate}>
            <h2 className="modal-title">New company</h2>

            <div className={modalFormBodyCls}>
              <div className="form-group">
                <label className="form-label" htmlFor="c-name">
                  Name *
                </label>
                <input
                  id="c-name"
                  className="form-input"
                  required
                  value={form.name}
                  onChange={(e) => {
                    setForm((f) => ({ ...f, name: e.target.value }));
                  }}
                  placeholder="Acme Corp"
                />
              </div>

              <div className="form-row">
                <div className="form-group">
                  <label className="form-label" htmlFor="c-ticker">
                    Ticker (optional)
                  </label>
                  <input
                    id="c-ticker"
                    className="form-input"
                    value={form.ticker}
                    onChange={(e) => {
                      setForm((f) => ({
                        ...f,
                        ticker: e.target.value.toUpperCase(),
                      }));
                    }}
                    placeholder="ACME"
                    maxLength={10}
                  />
                </div>
                <div className="form-group">
                  <label className="form-label" htmlFor="c-currency">
                    Currency
                  </label>
                  <input
                    id="c-currency"
                    className="form-input"
                    value={form.currency}
                    onChange={(e) => {
                      setForm((f) => ({
                        ...f,
                        currency: e.target.value.toUpperCase(),
                      }));
                    }}
                    placeholder="USD"
                    maxLength={3}
                  />
                </div>
              </div>
            </div>

            {createError && (
              <div className="alert alert-danger">{createError}</div>
            )}

            <div className={modalActionRowCls}>
              <button
                type="button"
                className="btn btn-secondary"
                onClick={() => {
                  setShowModal(false);
                  setForm(DEFAULT_FORM);
                  setCreateError(null);
                }}
              >
                Cancel
              </button>
              <button
                type="submit"
                className="btn btn-primary"
                disabled={creating || !form.name.trim()}
              >
                {creating ? <span className="spinner" /> : null}
                Create
              </button>
            </div>
          </form>
        </div>
      )}
    </div>
  );
}
