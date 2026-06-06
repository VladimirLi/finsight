"""Shared ORM → API-response hydration helpers.

These functions turn a ``FinancialPeriod`` ORM row (whose canonical line items
live in the ``statement_json`` blob) into the Pydantic response shapes declared
in :mod:`app.api.serializers`. They live here, rather than in any one router, so
the documents and companies routers produce byte-identical period payloads.
"""

from __future__ import annotations

from typing import Any

from app.api.serializers import FinancialValueOut, PeriodDetailOut
from app.db.models import FinancialPeriod
from app.schemas.financials import FinancialValue


def items_from_statement_json(
    statement_json: dict[str, Any] | None,
) -> dict[str, FinancialValueOut]:
    """Deserialise ``statement_json['items']`` into API ``FinancialValueOut`` shapes.

    Bare numeric values (as written by older versions) are tolerated and wrapped
    into a value-only ``FinancialValue``.
    """
    raw_items: dict[str, Any] = (statement_json or {}).get("items", {})
    result: dict[str, FinancialValueOut] = {}
    for key, raw_val in raw_items.items():
        if isinstance(raw_val, dict):
            fv = FinancialValue.model_validate(raw_val)
        else:
            fv = FinancialValue(value=float(raw_val) if raw_val is not None else None)
        result[key] = FinancialValueOut(
            value=fv.value,
            source_page=fv.source_page,
            source_label=fv.source_label,
            confidence=fv.confidence,
            edited_by_user=fv.edited_by_user,
        )
    return result


def period_to_detail(period: FinancialPeriod) -> PeriodDetailOut:
    """Convert a ``FinancialPeriod`` row to ``PeriodDetailOut`` (full items + provenance)."""
    company_name: str | None = None
    if period.company is not None:  # pyright: ignore[reportUnnecessaryComparison]  # SQLAlchemy relationship may be unloaded/None
        company_name = period.company.name
    return PeriodDetailOut(
        id=period.id,
        company_id=period.company_id,
        company_name=company_name,
        period_type=period.period_type,
        fiscal_year=period.fiscal_year,
        fiscal_period_end=period.fiscal_period_end,
        currency=period.currency,
        items=items_from_statement_json(period.statement_json),
    )
