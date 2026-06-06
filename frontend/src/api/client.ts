/**
 * Typed API client for finsight.
 *
 * All requests are routed through /api (proxied to localhost:8000 by Vite).
 * Throws an ApiError with the server's detail message on non-2xx responses.
 */

import type {
  DocumentT,
  DocumentDetail,
  PeriodDetail,
  Company,
  CompanyDetail,
  RatioReport,
  PeriodRatios,
  ValidationReport,
} from "./types";

// ---------------------------------------------------------------------------
// Error type
// ---------------------------------------------------------------------------
class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

// ---------------------------------------------------------------------------
// Core fetch helper
// ---------------------------------------------------------------------------
async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const url = `/api${path}`;

  // Build extra headers as a plain Record so we can spread safely
  const extraHeaders: Record<string, string> =
    options.body && !(options.body instanceof FormData)
      ? { "Content-Type": "application/json" }
      : {};

  // options.headers can be Headers | string[][] | Record<string,string> | undefined.
  // Normalise to a plain record for safe spreading.
  const existingHeaders: Record<string, string> =
    options.headers instanceof Headers
      ? Object.fromEntries(options.headers.entries())
      : Array.isArray(options.headers)
        ? Object.fromEntries(options.headers)
        : (options.headers ?? {});

  const res = await fetch(url, {
    ...options,
    headers: {
      Accept: "application/json",
      ...extraHeaders,
      ...existingHeaders,
    },
  });

  if (!res.ok) {
    let detail = `HTTP ${String(res.status)}`;
    try {
      const err = (await res.json()) as { detail?: string };
      if (err.detail) detail = err.detail;
    } catch {
      // ignore parse errors; use status text
      detail = res.statusText || detail;
    }
    throw new ApiError(res.status, detail);
  }

  // 204 No Content
  if (res.status === 204) return undefined as unknown as T;

  return res.json() as Promise<T>;
}

// ---------------------------------------------------------------------------
// Documents
// ---------------------------------------------------------------------------
export function listDocuments(): Promise<DocumentT[]> {
  return request("/documents");
}

export function getDocument(id: number): Promise<DocumentDetail> {
  return request(`/documents/${String(id)}`);
}

export function uploadDocument(
  file: File,
  companyId?: number,
): Promise<DocumentT> {
  const form = new FormData();
  form.append("file", file);
  if (companyId != null) form.append("company_id", String(companyId));
  return request("/documents/upload", { method: "POST", body: form });
}

export function reprocessDocument(id: number): Promise<DocumentT> {
  return request(`/documents/${String(id)}/reprocess`, { method: "POST" });
}

export function deleteDocument(id: number): Promise<{ ok: boolean }> {
  return request(`/documents/${String(id)}`, { method: "DELETE" });
}

// ---------------------------------------------------------------------------
// Periods
// ---------------------------------------------------------------------------
export function getPeriod(periodId: number): Promise<PeriodDetail> {
  return request(`/periods/${String(periodId)}`);
}

export function patchPeriodItems(
  periodId: number,
  updates: Record<string, number | null>,
): Promise<PeriodDetail> {
  return request(`/periods/${String(periodId)}/items`, {
    method: "PATCH",
    body: JSON.stringify({ updates }),
  });
}

// ---------------------------------------------------------------------------
// Ratios
// ---------------------------------------------------------------------------
export interface RatioParams {
  market_price?: number;
  shares_outstanding?: number;
}

export function getPeriodRatios(
  periodId: number,
  params?: RatioParams,
): Promise<RatioReport> {
  const qs = new URLSearchParams();
  if (params?.market_price != null)
    qs.set("market_price", String(params.market_price));
  if (params?.shares_outstanding != null)
    qs.set("shares_outstanding", String(params.shares_outstanding));
  const query = qs.toString() ? `?${qs.toString()}` : "";
  return request(`/periods/${String(periodId)}/ratios${query}`);
}

// ---------------------------------------------------------------------------
// Companies
// ---------------------------------------------------------------------------
export function listCompanies(): Promise<Company[]> {
  return request("/companies");
}

export function getCompany(id: number): Promise<CompanyDetail> {
  return request(`/companies/${String(id)}`);
}

export function createCompany(body: {
  name: string;
  ticker?: string;
  currency?: string;
}): Promise<Company> {
  return request("/companies", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function getCompanyRatios(
  companyId: number,
): Promise<{ periods: PeriodRatios[] }> {
  return request(`/companies/${String(companyId)}/ratios`);
}

// ---------------------------------------------------------------------------
// Validation (accounting identity checks)
// ---------------------------------------------------------------------------
export function getPeriodValidation(
  periodId: number,
): Promise<ValidationReport> {
  return request(`/periods/${String(periodId)}/validation`);
}
