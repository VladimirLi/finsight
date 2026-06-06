"""Canonical financial data model.

This is THE shared contract between the extraction pipeline (OCR + LLM) and the
deterministic ratio engine. The LLM's job is to map messy, OCR'd statement tables
onto these canonical keys. The ratio engine ONLY reads these keys, never raw text.

Design principles
-----------------
* Every monetary value is optional. A statement that does not report a line item
  leaves it as ``None`` -> the ratio engine reports the dependent metric as
  "unavailable" rather than guessing.
* Each extracted value carries provenance (source page, the raw label seen on the
  document, and a model confidence) so the UI can show where a number came from
  and let a human verify/override it.
* Values are stored in a single reporting currency and scale (actual units, not
  "in thousands"); the extraction layer is responsible for de-scaling.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class StatementType(StrEnum):
    """The kind of financial statement a document represents."""

    income_statement = "income_statement"
    balance_sheet = "balance_sheet"
    cash_flow = "cash_flow"


class PeriodType(StrEnum):
    """The reporting cadence of a financial period."""

    fiscal_year = "FY"
    quarter = "Q"
    half_year = "H"
    ttm = "TTM"


class FinancialValue(BaseModel):
    """A single extracted (or human-corrected) monetary figure with provenance."""

    model_config = ConfigDict(strict=True)

    value: float | None = Field(
        default=None,
        description="Value in actual reporting-currency units (NOT thousands/millions).",
    )
    source_page: int | None = Field(
        default=None, description="1-based PDF page the value was read from."
    )
    source_label: str | None = Field(
        default=None,
        description="The verbatim row label seen on the document, e.g. 'Total current assets'.",
    )
    confidence: float | None = Field(
        default=None, ge=0.0, le=1.0, description="Extractor confidence 0..1."
    )
    edited_by_user: bool = Field(
        default=False, description="True if a human reviewed/overrode this value."
    )


# ---------------------------------------------------------------------------
# Canonical line-item keys, grouped by statement. The string values here are the
# ONLY identifiers the ratio engine and the extraction schema may use.
# ---------------------------------------------------------------------------

INCOME_STATEMENT_FIELDS = [
    "revenue",
    "cost_of_goods_sold",
    "gross_profit",
    "operating_expenses",
    "research_and_development",
    "selling_general_admin",
    "depreciation_amortization",
    "operating_income",  # EBIT
    "interest_expense",
    "interest_income",
    "pretax_income",
    "income_tax_expense",
    "net_income",
    "ebitda",
    "shares_outstanding_diluted",
    "shares_outstanding_basic",
    "eps_diluted",
]

BALANCE_SHEET_FIELDS = [
    "cash_and_equivalents",
    "short_term_investments",
    "accounts_receivable",
    "inventory",
    "prepaid_expenses",
    "other_current_assets",
    "total_current_assets",
    "property_plant_equipment_net",
    "goodwill",
    "intangible_assets",
    "long_term_investments",
    "other_non_current_assets",
    "total_non_current_assets",
    "total_assets",
    "accounts_payable",
    "short_term_debt",
    "accrued_liabilities",
    "deferred_revenue_current",
    "other_current_liabilities",
    "total_current_liabilities",
    "long_term_debt",
    "deferred_tax_liabilities",
    "other_non_current_liabilities",
    "total_non_current_liabilities",
    "total_liabilities",
    "common_stock",
    "retained_earnings",
    "treasury_stock",
    "total_equity",  # total shareholders' equity
    "minority_interest",
]

CASH_FLOW_FIELDS = [
    "operating_cash_flow",
    "depreciation_amortization_cf",
    "stock_based_compensation",
    "change_in_working_capital",
    "capital_expenditures",  # usually negative as reported; store as reported
    "acquisitions",
    "investing_cash_flow",
    "debt_issued",
    "debt_repaid",
    "dividends_paid",
    "share_repurchases",
    "financing_cash_flow",
    "free_cash_flow",
    "net_change_in_cash",
]

ALL_CANONICAL_FIELDS = INCOME_STATEMENT_FIELDS + BALANCE_SHEET_FIELDS + CASH_FLOW_FIELDS


class FinancialStatement(BaseModel):
    """All canonical line items for a single company-period.

    A period may be assembled from one or several uploaded documents (e.g. a 10-K
    contributes the income statement, balance sheet, and cash flow together).
    Unreported items stay as default ``FinancialValue()`` with ``value=None``.

    ``strict=True`` ensures that malformed LLM data (string numbers, etc.) is
    rejected at the model boundary rather than silently coerced. The extraction
    pipeline is responsible for converting raw values to proper Python types
    before constructing this model.
    """

    model_config = ConfigDict(strict=True)

    company_name: str | None = None
    ticker: str | None = None
    currency: str | None = Field(default=None, description="ISO 4217, e.g. 'USD'.")
    # strict=False on this field only: model_dump(mode="json") serialises the enum to its
    # string value ("FY"); the DB round-trip then re-validates that string. Under the
    # model-wide strict=True a plain str would be rejected for an enum field, so we allow
    # coercion here while keeping every numeric field strict (the whole point of strict).
    period_type: PeriodType | None = Field(default=None, strict=False)
    fiscal_year: int | None = None
    fiscal_period_end: str | None = Field(
        default=None, description="ISO date 'YYYY-MM-DD' of period end."
    )
    units_scale_note: str | None = Field(
        default=None,
        description="What the source reported in, e.g. 'in thousands' (for audit).",
    )

    # canonical line items
    items: dict[str, FinancialValue] = Field(default_factory=dict)

    def get(self, key: str) -> float | None:
        """Return the numeric value for a canonical key, or None if absent."""
        fv = self.items.get(key)
        return fv.value if fv else None
