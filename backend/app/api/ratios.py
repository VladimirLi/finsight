"""Ratio computation endpoint.

GET /periods/{period_id}/ratios?market_price=&shares_outstanding=
    → RatioReport

Market params are optional query parameters; valuation ratios that depend on them
will be reported as ``unavailable`` when the params are absent.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.serializers import (
    IdentityResultOut,
    RatioReportOut,
    RatioResultOut,
    ValidationReportOut,
)
from app.db.database import get_db
from app.db.models import FinancialPeriod

router = APIRouter()


# ---------------------------------------------------------------------------
# Route
# ---------------------------------------------------------------------------


@router.get("/periods/{period_id}/ratios", response_model=RatioReportOut)
def get_period_ratios(
    period_id: int,
    market_price: float | None = Query(
        default=None,
        description="Current share price in reporting currency. Required for valuation ratios.",
    ),
    shares_outstanding: float | None = Query(
        default=None,
        description=(
            "Shares outstanding (absolute count, not millions). "
            "Required for market-cap-based valuation ratios. "
            "Falls back to the value extracted from the income statement when absent."
        ),
    ),
    db: Session = Depends(get_db),
) -> RatioReportOut:
    """Compute all financial ratios for the given period.

    Ratios are computed deterministically from the stored canonical line items —
    never by an LLM.  Each result carries a ``status``:
    - ``ok``          — value computed successfully
    - ``unavailable`` — one or more required inputs were missing
    - ``undefined``   — math is undefined (e.g. division by zero)

    Pass ``market_price`` and/or ``shares_outstanding`` to unlock valuation
    ratios (P/E, EV/EBITDA, etc.).  Omitting them leaves those ratios as
    ``unavailable`` rather than erroring.
    """
    # Lazy import: keeps the app importable without the ratio engine fully wired.
    from app.extraction import service as extraction_service  # noqa: PLC0415
    from app.ratios.engine import compute_all_ratios  # noqa: PLC0415

    period: FinancialPeriod | None = (
        db.query(FinancialPeriod).filter(FinancialPeriod.id == period_id).first()
    )
    if period is None:
        raise HTTPException(status_code=404, detail=f"Period {period_id} not found.")

    statement = extraction_service.get_statement(period)

    # Build the optional market_data dict; only include keys the caller provided.
    market_data: dict[str, float] = {}
    if market_price is not None:
        market_data["market_price"] = market_price
    if shares_outstanding is not None:
        market_data["shares_outstanding"] = shares_outstanding

    ratio_results = compute_all_ratios(statement, market_data=market_data)

    return RatioReportOut(
        period_id=period_id,
        results=[RatioResultOut(**r.to_dict()) for r in ratio_results],
    )


@router.get("/periods/{period_id}/validation", response_model=ValidationReportOut)
def get_period_validation(
    period_id: int,
    db: Session = Depends(get_db),
) -> ValidationReportOut:
    """Run deterministic accounting-identity checks for the given period.

    Verifies accounting equations (assets = liabilities + equity, subtotals foot to
    totals, gross_profit = revenue - COGS, etc.) within a rounding tolerance. Each
    result carries a ``status``:
    - ``ok``          — the identity holds within tolerance
    - ``mismatch``    — the figures do not reconcile (likely an extraction error)
    - ``unavailable`` — one or more required line items were not reported

    Like ratios, these are computed in pure Python, never by an LLM, so the UI can
    flag inconsistent extractions instead of trusting bad data silently.
    """
    from app.extraction import service as extraction_service  # noqa: PLC0415
    from app.validation.engine import validate_statement  # noqa: PLC0415

    period: FinancialPeriod | None = (
        db.query(FinancialPeriod).filter(FinancialPeriod.id == period_id).first()
    )
    if period is None:
        raise HTTPException(status_code=404, detail=f"Period {period_id} not found.")

    statement = extraction_service.get_statement(period)
    results = validate_statement(statement)

    summary: dict[str, int] = {}
    for r in results:
        summary[r.status.value] = summary.get(r.status.value, 0) + 1

    return ValidationReportOut(
        period_id=period_id,
        results=[IdentityResultOut(**r.to_dict()) for r in results],
        summary=summary,
    )
