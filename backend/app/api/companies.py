"""Company and Period endpoints.

Companies
---------
GET  /companies              → Company[]
POST /companies              → Company
GET  /companies/{id}         → CompanyDetail
GET  /companies/{id}/ratios  → { periods: PeriodRatios[] }

Periods
-------
GET   /periods/{period_id}        → PeriodDetail
POST  /periods                    → PeriodDetail  (manual period creation)
PATCH /periods/{period_id}/items  → PeriodDetail  (inline corrections)

Ratio routes that require a period ID live in ratios.py to keep each path
declared exactly once across the codebase.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload

from app.api._hydrate import period_to_detail
from app.api.serializers import (
    CompanyDetailOut,
    CompanyOut,
    CompanyRatioTrendOut,
    CreateCompanyIn,
    CreatePeriodIn,
    PatchItemsIn,
    PeriodDetailOut,
    PeriodRatiosOut,
    PeriodSummaryOut,
    RatioResultOut,
)
from app.db.database import get_db
from app.db.models import Company, FinancialPeriod

router = APIRouter()


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _period_to_summary(period: FinancialPeriod) -> PeriodSummaryOut:
    return PeriodSummaryOut(
        id=period.id,
        period_type=period.period_type,
        fiscal_year=period.fiscal_year,
        fiscal_period_end=period.fiscal_period_end,
    )


def _get_company_or_404(db: Session, company_id: int) -> Company:
    company = (
        db.query(Company)
        .options(joinedload(Company.periods))
        .filter(Company.id == company_id)
        .first()
    )
    if company is None:
        raise HTTPException(status_code=404, detail=f"Company {company_id} not found.")
    return company


def _get_period_or_404(db: Session, period_id: int) -> FinancialPeriod:
    period = (
        db.query(FinancialPeriod)
        .options(joinedload(FinancialPeriod.company))
        .filter(FinancialPeriod.id == period_id)
        .first()
    )
    if period is None:
        raise HTTPException(status_code=404, detail=f"Period {period_id} not found.")
    return period


# ---------------------------------------------------------------------------
# Company routes
# ---------------------------------------------------------------------------


@router.get("/companies", response_model=list[CompanyOut])
def list_companies(db: Session = Depends(get_db)) -> list[CompanyOut]:
    """Return all companies ordered by name."""
    companies = db.query(Company).order_by(Company.name).all()
    return [
        CompanyOut(id=c.id, name=c.name, ticker=c.ticker, currency=c.currency) for c in companies
    ]


@router.post("/companies", response_model=CompanyOut, status_code=201)
def create_company(body: CreateCompanyIn, db: Session = Depends(get_db)) -> CompanyOut:
    """Create a new company record."""
    company = Company(
        name=body.name,
        ticker=body.ticker,
        currency=body.currency,
    )
    db.add(company)
    db.commit()
    db.refresh(company)
    return CompanyOut(
        id=company.id,
        name=company.name,
        ticker=company.ticker,
        currency=company.currency,
    )


@router.get("/companies/{company_id}", response_model=CompanyDetailOut)
def get_company(company_id: int, db: Session = Depends(get_db)) -> CompanyDetailOut:
    """Return a company with its associated period summaries."""
    company = _get_company_or_404(db, company_id)
    periods = sorted(company.periods, key=lambda p: (p.fiscal_year or 0, p.id))
    return CompanyDetailOut(
        id=company.id,
        name=company.name,
        ticker=company.ticker,
        currency=company.currency,
        periods=[_period_to_summary(p) for p in periods],
    )


@router.get("/companies/{company_id}/ratios", response_model=CompanyRatioTrendOut)
def get_company_ratios(company_id: int, db: Session = Depends(get_db)) -> CompanyRatioTrendOut:
    """Compute ratios for every period belonging to the company.

    Returns a time-series suitable for trend charts. Valuation ratios that require
    market data will be ``unavailable`` here — use GET /periods/{id}/ratios with
    query params for those.
    """
    # Lazy import keeps the app importable without ratio engine deps.
    from app.extraction import service as extraction_service  # noqa: PLC0415
    from app.ratios.engine import compute_all_ratios  # noqa: PLC0415

    company = _get_company_or_404(db, company_id)
    periods = sorted(company.periods, key=lambda p: (p.fiscal_year or 0, p.id))

    period_ratios: list[PeriodRatiosOut] = []
    for period in periods:
        statement = extraction_service.get_statement(period)
        ratio_results = compute_all_ratios(statement, market_data={})
        period_ratios.append(
            PeriodRatiosOut(
                period=_period_to_summary(period),
                results=[RatioResultOut(**r.to_dict()) for r in ratio_results],
            )
        )

    return CompanyRatioTrendOut(periods=period_ratios)


# ---------------------------------------------------------------------------
# Period routes
# ---------------------------------------------------------------------------


@router.get("/periods/{period_id}", response_model=PeriodDetailOut)
def get_period(period_id: int, db: Session = Depends(get_db)) -> PeriodDetailOut:
    """Return a single period with its full canonical items and provenance."""
    period = _get_period_or_404(db, period_id)
    return period_to_detail(period)


@router.post("/periods", response_model=PeriodDetailOut, status_code=201)
def create_period(body: CreatePeriodIn, db: Session = Depends(get_db)) -> PeriodDetailOut:
    """Manually create a blank period (no documents attached yet).

    Useful for entering historical data manually via the review UI before any
    document has been uploaded.
    """
    # Verify the target company exists.
    company = db.query(Company).filter(Company.id == body.company_id).first()
    if company is None:
        raise HTTPException(
            status_code=404,
            detail=f"Company {body.company_id} not found.",
        )

    period = FinancialPeriod(
        company_id=body.company_id,
        period_type=body.period_type,
        fiscal_year=body.fiscal_year,
        fiscal_period_end=body.fiscal_period_end,
        currency=company.currency,  # inherit company default
        statement_json={"items": {}},
    )
    db.add(period)
    db.commit()
    db.refresh(period)
    # Reload with company relationship for name field.
    period = _get_period_or_404(db, period.id)
    return period_to_detail(period)


@router.patch("/periods/{period_id}/items", response_model=PeriodDetailOut)
def patch_period_items(
    period_id: int,
    body: PatchItemsIn,
    db: Session = Depends(get_db),
) -> PeriodDetailOut:
    """Apply human corrections to individual line items.

    Each key in ``updates`` is a canonical field name; the value is the new
    number (or ``null`` to clear it).  Touched entries are flagged
    ``edited_by_user=true`` so provenance is preserved.

    Delegates to ``app.extraction.service.apply_item_updates`` which owns the
    merge logic so the pipeline and the review UI stay in sync.
    """
    # Lazy import to keep the app importable without extraction deps.
    from app.extraction import service as extraction_service  # noqa: PLC0415

    period = _get_period_or_404(db, period_id)

    # Delegate the mutation to the extraction service layer.
    updated_period = extraction_service.apply_item_updates(
        db=db,
        period=period,
        updates=body.updates,
    )

    return period_to_detail(updated_period)
