"""Pydantic response models that map the DB ORM objects to the API response shapes.

These models ARE the API contract: FastAPI emits them into the OpenAPI schema
(``backend/openapi.json``), from which the frontend's TypeScript types are generated
(``frontend/src/api/openapi.d.ts``). Optional fields are typed ``| None`` so the JSON
serializer omits nothing and front-end deserialization is predictable.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

# ---------------------------------------------------------------------------
# Shared primitives
# ---------------------------------------------------------------------------


class FinancialValueOut(BaseModel):
    """Mirrors TS interface FinancialValue."""

    value: float | None
    source_page: int | None
    source_label: str | None
    confidence: float | None
    edited_by_user: bool

    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# Period models
# ---------------------------------------------------------------------------


class PeriodSummaryOut(BaseModel):
    """Mirrors TS interface PeriodSummary — lightweight, used in list responses."""

    id: int
    period_type: str | None
    fiscal_year: int | None
    fiscal_period_end: str | None

    model_config = ConfigDict(from_attributes=True)


class PeriodDetailOut(BaseModel):
    """Mirrors TS interface PeriodDetail — full canonical items with provenance."""

    id: int
    company_id: int
    company_name: str | None
    period_type: str | None
    fiscal_year: int | None
    fiscal_period_end: str | None
    currency: str | None
    # key → FinancialValue dict; keys are canonical line-item names
    items: dict[str, FinancialValueOut]

    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# Document models
# ---------------------------------------------------------------------------


class DocumentOut(BaseModel):
    """Mirrors TS interface Document."""

    id: int
    filename: str
    status: str
    num_pages: int | None
    error: str | None
    detected_statement_types: list[str] | None
    period_id: int | None
    created_at: str  # ISO-8601 string; we format in the router

    model_config = ConfigDict(from_attributes=True)


class DocumentDetailOut(DocumentOut):
    """Mirrors TS interface DocumentDetail — adds the associated period."""

    period: PeriodDetailOut | None


# ---------------------------------------------------------------------------
# Company models
# ---------------------------------------------------------------------------


class CompanyOut(BaseModel):
    """Mirrors TS interface Company."""

    id: int
    name: str
    ticker: str | None
    currency: str | None

    model_config = ConfigDict(from_attributes=True)


class CompanyDetailOut(CompanyOut):
    """Mirrors TS interface CompanyDetail — includes period summaries."""

    periods: list[PeriodSummaryOut]


# ---------------------------------------------------------------------------
# Ratio models
# ---------------------------------------------------------------------------


class RatioResultOut(BaseModel):
    """Mirrors TS interface RatioResult."""

    key: str
    name: str
    category: str
    status: str  # "ok" | "unavailable" | "undefined"
    value: float | None
    unit: str
    missing_inputs: list[str]
    detail: str | None


class RatioReportOut(BaseModel):
    """Mirrors TS interface RatioReport."""

    period_id: int
    results: list[RatioResultOut]


class PeriodRatiosOut(BaseModel):
    """Mirrors TS interface PeriodRatios — one period + its ratio results."""

    period: PeriodSummaryOut
    results: list[RatioResultOut]


class CompanyRatioTrendOut(BaseModel):
    """Response body for GET /companies/{id}/ratios."""

    periods: list[PeriodRatiosOut]


class IdentityResultOut(BaseModel):
    """One accounting-identity check result (mirrors validation.IdentityResult)."""

    key: str
    name: str
    status: str  # "ok" | "mismatch" | "unavailable"
    lhs: float | None
    rhs: float | None
    difference: float | None
    tolerance: float | None
    missing_inputs: list[str]
    detail: str | None


class ValidationReportOut(BaseModel):
    """Accounting-identity validation for a single period."""

    period_id: int
    results: list[IdentityResultOut]
    summary: dict[str, int]


# ---------------------------------------------------------------------------
# Simple success / request bodies
# ---------------------------------------------------------------------------


class OkOut(BaseModel):
    """Generic success response body."""

    ok: bool = True


class CreateCompanyIn(BaseModel):
    """Request body for creating a company."""

    name: str
    ticker: str | None = None
    currency: str | None = None


class CreatePeriodIn(BaseModel):
    """Request body for creating a financial period."""

    company_id: int
    period_type: str | None = None
    fiscal_year: int | None = None
    fiscal_period_end: str | None = None


class PatchItemsIn(BaseModel):
    """Body for PATCH /periods/{period_id}/items."""

    # canonical_key → number | null
    updates: dict[str, float | None]
