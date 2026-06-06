import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { css } from "../../styled-system/css";
import {
  listDocuments,
  deleteDocument,
  reprocessDocument,
} from "../api/client";
import type { DocumentT } from "../api/types";
import StatusBadge from "../components/StatusBadge";

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

const docErrorCls = css({
  fontSize: "xs",
  color: "mismatch",
  marginTop: "[2px]", // escape hatch: 0.5 is not in spacing tokens; 2px matches original
});

// Statement type badge — brandBg background, brand foreground, right margin
const stmtTypeBadgeCls = css({
  marginRight: "1",
  background: "brandBg",
  color: "brand",
});

const actionsCellCls = css({
  display: "flex",
  gap: "2",
  flexWrap: "wrap",
});

export default function DocumentsPage() {
  const [docs, setDocs] = useState<DocumentT[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [actionId, setActionId] = useState<number | null>(null);

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await listDocuments();
      // Most recent first
      setDocs(data.slice().sort((a, b) => b.id - a.id));
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to load documents");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
  }, []);

  const handleDelete = async (id: number) => {
    if (!confirm("Delete this document? This cannot be undone.")) return;
    setActionId(id);
    try {
      await deleteDocument(id);
      setDocs((prev) => prev.filter((d) => d.id !== id));
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : "Delete failed");
    } finally {
      setActionId(null);
    }
  };

  const handleReprocess = async (id: number) => {
    setActionId(id);
    try {
      const updated = await reprocessDocument(id);
      setDocs((prev) => prev.map((d) => (d.id === updated.id ? updated : d)));
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : "Reprocess failed");
    } finally {
      setActionId(null);
    }
  };

  return (
    <div>
      <div className={`page-header ${pageHeaderRowCls}`}>
        <div>
          <h1 className="page-title">Documents</h1>
          <p className="page-subtitle">All uploaded financial statement PDFs</p>
        </div>
        <Link to="/upload" className="btn btn-primary">
          + Upload
        </Link>
      </div>

      {loading && (
        <div className={centerSpinnerCls}>
          <span className="spinner spinner-lg" />
        </div>
      )}

      {error && <div className="alert alert-danger">{error}</div>}

      {!loading && docs.length === 0 && (
        <div className="empty-state card">
          <div className="empty-state-icon">&#x1F4C4;</div>
          <div className="empty-state-title">No documents yet</div>
          <p>Upload a PDF to get started.</p>
          <div className={emptyStateBtnMtCls}>
            <Link to="/upload" className="btn btn-primary">
              Upload document
            </Link>
          </div>
        </div>
      )}

      {!loading && docs.length > 0 && (
        <div className="card">
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>File</th>
                  <th>Status</th>
                  <th>Pages</th>
                  <th>Detected types</th>
                  <th>Uploaded</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {docs.map((doc) => (
                  <tr key={doc.id}>
                    <td>
                      <span className="font-semibold">{doc.filename}</span>
                      {doc.error && (
                        <div className={docErrorCls} title={doc.error}>
                          {doc.error.slice(0, 80)}
                          {doc.error.length > 80 ? "…" : ""}
                        </div>
                      )}
                    </td>
                    <td>
                      <StatusBadge status={doc.status} />
                    </td>
                    <td className="text-muted">{doc.num_pages ?? "—"}</td>
                    <td>
                      {doc.detected_statement_types?.map((t) => (
                        <span key={t} className={`badge ${stmtTypeBadgeCls}`}>
                          {t.replace(/_/g, " ")}
                        </span>
                      )) ?? <span className="text-muted">—</span>}
                    </td>
                    <td className="text-muted text-sm">
                      {new Date(doc.created_at).toLocaleDateString()}
                    </td>
                    <td>
                      <div className={actionsCellCls}>
                        {/* Review link — available once we have a period */}
                        {doc.period_id && (
                          <Link
                            to={`/review/${String(doc.period_id)}`}
                            className="btn btn-secondary btn-sm"
                          >
                            Review
                          </Link>
                        )}
                        {/* Reprocess */}
                        {(doc.status === "failed" ||
                          doc.status === "ready" ||
                          doc.status === "needs_review") && (
                          <button
                            className="btn btn-secondary btn-sm"
                            disabled={actionId === doc.id}
                            onClick={() => handleReprocess(doc.id)}
                          >
                            {actionId === doc.id ? (
                              <span className="spinner" />
                            ) : null}
                            Reprocess
                          </button>
                        )}
                        {/* Delete */}
                        <button
                          className="btn btn-danger btn-sm"
                          disabled={actionId === doc.id}
                          onClick={() => handleDelete(doc.id)}
                        >
                          Delete
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
