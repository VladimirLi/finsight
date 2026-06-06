import { useState, useRef, useCallback, useEffect } from "react";
import { Link } from "react-router-dom";
import { css } from "../../styled-system/css";
import { uploadDocument, getDocument, listCompanies } from "../api/client";
import type { DocumentT, Company, DocStatus } from "../api/types";
import StatusBadge from "../components/StatusBadge";

// Statuses that represent a terminal or reviewable state
const POLLING_DONE: DocStatus[] = ["needs_review", "ready", "failed"];

// Pipeline step definitions in order
const PIPELINE_STEPS: { key: DocStatus | "done"; label: string }[] = [
  { key: "parsing", label: "Parsing" },
  { key: "extracting", label: "Extracting" },
  { key: "needs_review", label: "Needs Review" },
  { key: "ready", label: "Ready" },
];

function stepState(
  status: DocStatus,
  stepKey: string,
): "done" | "active" | "pending" | "error" {
  if (status === "failed") return "error";
  const order: string[] = [
    "uploaded",
    "parsing",
    "extracting",
    "needs_review",
    "ready",
  ];
  const statusIdx = order.indexOf(status);
  const stepIdx = order.indexOf(stepKey);
  if (statusIdx < 0 || stepIdx < 0) return "pending";
  if (stepIdx < statusIdx) return "done";
  if (stepIdx === statusIdx) return "active";
  return "pending";
}

// ---------------------------------------------------------------------------
// Panda css() utility classes
// ---------------------------------------------------------------------------

const uploadCardMbCls = css({ marginBottom: "6" });

const cardBodyFlexCls = css({
  display: "flex",
  flexDirection: "column",
  gap: "6",
});

// File input hidden
const hiddenInputCls = css({ display: "none" });

// Company selector row: auto cols
const companySelectorRowCls = css({
  // override the default 1fr 1fr form-row grid
  gridTemplateColumns: "[1fr auto]", // escape hatch: no grid token for this value
});

const uploadBtnGroupCls = css({
  display: "flex",
  alignItems: "flex-end",
  gap: "2",
});

// Polling alert — row alignment
const pollingAlertCls = css({ alignItems: "center" });

// Error detail inside failed-doc card
const errorDetailCls = css({ marginTop: "[4px]" }); // escape hatch: 0.5 not in spacing tokens; 4px matches original

// Detected statement types area — spacing token "2" = 0.5rem
const detectedLabelCls = css({ marginRight: "2" });

// Statement type badge — brandBg background, brand colour; marginRight "1" = 0.25rem matches "4px"
const stmtTypeBadgeCls = css({
  marginRight: "1",
  background: "brandBg",
  color: "brand",
});

const actionRowCls = css({
  display: "flex",
  gap: "3",
  flexWrap: "wrap",
});

export default function UploadPage() {
  const [dragOver, setDragOver] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const [companyId, setCompanyId] = useState<number | "">("");
  const [companies, setCompanies] = useState<Company[]>([]);
  const [uploading, setUploading] = useState(false);
  const [doc, setDoc] = useState<DocumentT | null>(null);
  const [error, setError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Load company list for the selector
  useEffect(() => {
    listCompanies()
      .then(setCompanies)
      .catch(() => {
        /* non-critical */
      });
  }, []);

  // Poll document status while pipeline is running
  useEffect(() => {
    if (!doc) return;
    if (POLLING_DONE.includes(doc.status)) return;

    pollRef.current = setInterval(async () => {
      try {
        const updated = await getDocument(doc.id);
        setDoc(updated);
        if (POLLING_DONE.includes(updated.status)) {
          if (pollRef.current) clearInterval(pollRef.current);
        }
      } catch {
        // ignore transient errors while polling
      }
    }, 2000);

    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, [doc?.id, doc?.status]); // eslint-disable-line react-hooks/exhaustive-deps

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    const dropped = e.dataTransfer.files[0];
    if (dropped?.type === "application/pdf" || dropped?.name.endsWith(".pdf")) {
      setFile(dropped);
      setDoc(null);
      setError(null);
    } else {
      setError("Only PDF files are supported.");
    }
  }, []);

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0];
    if (f) {
      setFile(f);
      setDoc(null);
      setError(null);
    }
  };

  const handleUpload = async () => {
    if (!file) return;
    setUploading(true);
    setError(null);
    setDoc(null);
    try {
      const result = await uploadDocument(
        file,
        companyId !== "" ? companyId : undefined,
      );
      setDoc(result);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Upload failed");
    } finally {
      setUploading(false);
    }
  };

  const handleReset = () => {
    setFile(null);
    setDoc(null);
    setError(null);
    if (fileInputRef.current) fileInputRef.current.value = "";
  };

  const isPolling = doc && !POLLING_DONE.includes(doc.status);
  const isDone = doc && POLLING_DONE.includes(doc.status);

  return (
    <div>
      <div className="page-header">
        <h1 className="page-title">Upload Financial Statement</h1>
        <p className="page-subtitle">
          Upload a PDF to extract line items and compute financial ratios.
        </p>
      </div>

      {/* Upload zone */}
      {!doc && (
        <div className={`card ${uploadCardMbCls}`}>
          <div className={`card-body ${cardBodyFlexCls}`}>
            <div
              className={`upload-zone${dragOver ? " drag-over" : ""}`}
              onDragOver={(e) => {
                e.preventDefault();
                setDragOver(true);
              }}
              onDragLeave={() => {
                setDragOver(false);
              }}
              onDrop={handleDrop}
              onClick={() => fileInputRef.current?.click()}
              role="button"
              tabIndex={0}
              onKeyDown={(e) =>
                e.key === "Enter" && fileInputRef.current?.click()
              }
            >
              <svg
                className="upload-zone-icon"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth={1.5}
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  d="M19.5 14.25v-2.625a3.375 3.375 0 00-3.375-3.375h-1.5A1.125 1.125 0 0113.5 7.125v-1.5a3.375 3.375 0 00-3.375-3.375H8.25m6.75 12l-3-3m0 0l-3 3m3-3v6m-1.5-15H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 00-9-9z"
                />
              </svg>

              {file ? (
                <>
                  <div className="upload-zone-title">{file.name}</div>
                  <div className="upload-zone-sub">
                    {(file.size / 1024).toFixed(0)} KB — click to change
                  </div>
                </>
              ) : (
                <>
                  <div className="upload-zone-title">Drop your PDF here</div>
                  <div className="upload-zone-sub">or click to browse</div>
                </>
              )}
              <input
                ref={fileInputRef}
                type="file"
                accept="application/pdf,.pdf"
                className={hiddenInputCls}
                onChange={handleFileChange}
              />
            </div>

            {/* Company selector */}
            <div className={`form-row ${companySelectorRowCls}`}>
              <div className="form-group">
                <label className="form-label" htmlFor="company-select">
                  Associate with company (optional)
                </label>
                <select
                  id="company-select"
                  className="form-select"
                  value={companyId}
                  onChange={(e) => {
                    setCompanyId(e.target.value ? Number(e.target.value) : "");
                  }}
                >
                  <option value="">— No company —</option>
                  {companies.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.name}
                      {c.ticker ? ` (${c.ticker})` : ""}
                    </option>
                  ))}
                </select>
              </div>

              <div className={uploadBtnGroupCls}>
                <button
                  className="btn btn-primary btn-lg"
                  disabled={!file || uploading}
                  onClick={handleUpload}
                >
                  {uploading ? <span className="spinner" /> : null}
                  {uploading ? "Uploading..." : "Upload & Process"}
                </button>
              </div>
            </div>

            {error && <div className="alert alert-danger">{error}</div>}
          </div>
        </div>
      )}

      {/* Pipeline progress */}
      {doc && (
        <div className="card">
          <div className="card-header">
            <span className="card-title">{doc.filename}</span>
            <StatusBadge status={doc.status} />
          </div>
          <div className={`card-body ${cardBodyFlexCls}`}>
            {/* Step indicators */}
            <div className="pipeline-steps">
              {PIPELINE_STEPS.map((step) => {
                const state = stepState(doc.status, step.key);
                return (
                  <div key={step.key} className={`pipeline-step step-${state}`}>
                    <div className="pipeline-step-dot">
                      {state === "done" ? "✓" : state === "error" ? "!" : ""}
                    </div>
                    <div className="pipeline-step-label">{step.label}</div>
                  </div>
                );
              })}
            </div>

            {/* Status messages */}
            {isPolling && (
              <div className={`alert alert-info ${pollingAlertCls}`}>
                <span className="spinner" />
                <span>Processing document — this may take a minute…</span>
              </div>
            )}

            {doc.status === "failed" && (
              <div className="alert alert-danger">
                <div>
                  <strong>Processing failed.</strong>
                  {doc.error && (
                    <div className={errorDetailCls}>{doc.error}</div>
                  )}
                </div>
              </div>
            )}

            {doc.status === "needs_review" && (
              <div className="alert alert-warning">
                Extraction complete — please review the extracted values before
                the ratios are finalised.
              </div>
            )}

            {doc.status === "ready" && (
              <div className="alert alert-success">
                Document is ready. All values reviewed and ratios computed.
              </div>
            )}

            {/* Detected statement types */}
            {doc.detected_statement_types &&
              doc.detected_statement_types.length > 0 && (
                <div>
                  <span className={`text-sm text-muted ${detectedLabelCls}`}>
                    Detected:
                  </span>
                  {doc.detected_statement_types.map((t) => (
                    <span key={t} className={`badge ${stmtTypeBadgeCls}`}>
                      {t.replace(/_/g, " ")}
                    </span>
                  ))}
                </div>
              )}

            {/* Actions */}
            <div className={actionRowCls}>
              {isDone && doc.period_id && (
                <Link
                  to={`/review/${String(doc.period_id)}`}
                  className="btn btn-primary"
                >
                  Review & Ratios
                </Link>
              )}
              <button className="btn btn-secondary" onClick={handleReset}>
                Upload another
              </button>
              <Link to="/documents" className="btn btn-secondary">
                All documents
              </Link>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
