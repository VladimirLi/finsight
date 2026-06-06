"""JSON schema the LLM must return when extracting a financial statement.

The schema mirrors :class:`app.schemas.financials.FinancialStatement` but is shaped
for an LLM: every canonical line item is an *object* carrying the numeric value plus
provenance (source page, the verbatim row label, and a confidence). The canonical key
list is injected dynamically from :data:`ALL_CANONICAL_FIELDS` so this schema can never
drift from the shared contract.

The pipeline passes :func:`build_extraction_schema` straight to
``LLMProvider.extract_json(..., json_schema=...)``. Providers either constrain the model
natively (Anthropic tool-use / OpenAI response_format) or inject the schema into the
prompt and parse the result; either way this is the single source of truth for shape.
"""

from __future__ import annotations

from typing import Any

from app.schemas.financials import (
    ALL_CANONICAL_FIELDS,
    BALANCE_SHEET_FIELDS,
    CASH_FLOW_FIELDS,
    INCOME_STATEMENT_FIELDS,
)

# ---------------------------------------------------------------------------
# Human-readable descriptions / synonym hints per canonical field.
#
# These descriptions are embedded in the schema so the model maps the messy,
# real-world row labels it sees on a statement (e.g. "Total current assets",
# "Cost of sales", "PP&E, net") onto the correct canonical key. Anything not
# explicitly described still gets a sensible generic description (see below),
# but the high-value / easily-confused items are spelled out here.
# ---------------------------------------------------------------------------
_FIELD_DESCRIPTIONS: dict[str, str] = {
    # --- income statement ---
    "revenue": "Total revenue / net sales / total net revenues / turnover.",
    "cost_of_goods_sold": "Cost of goods sold / cost of sales / cost of revenue.",
    "gross_profit": "Gross profit / gross margin (revenue minus COGS) AS REPORTED.",
    "operating_expenses": "Total operating expenses (excludes COGS).",
    "research_and_development": "Research and development (R&D) expense.",
    "selling_general_admin": "Selling, general & administrative (SG&A) expense.",
    "depreciation_amortization": "Depreciation & amortization shown on the income statement.",
    "operating_income": "Operating income / operating profit / income from operations (EBIT).",
    "interest_expense": "Interest expense (financing cost). Report as a positive number.",
    "interest_income": "Interest income / investment income.",
    "pretax_income": "Income before income taxes / pretax income.",
    "income_tax_expense": "Provision for income taxes / income tax expense.",
    "net_income": "Net income / net earnings / profit for the year (attributable to the company).",
    "ebitda": "EBITDA only if explicitly reported on the document; do NOT compute it.",
    "shares_outstanding_diluted": "Diluted weighted-average shares outstanding (a share count, not money).",
    "shares_outstanding_basic": "Basic weighted-average shares outstanding (a share count, not money).",
    "eps_diluted": "Diluted earnings per share (a per-share figure, not total money).",
    # --- balance sheet: assets ---
    "cash_and_equivalents": "Cash and cash equivalents.",
    "short_term_investments": "Short-term / marketable investments / securities.",
    "accounts_receivable": "Accounts receivable, net / trade receivables.",
    "inventory": "Inventory / inventories, net.",
    "prepaid_expenses": "Prepaid expenses.",
    "other_current_assets": "Other current assets.",
    "total_current_assets": "Total current assets (the reported subtotal).",
    "property_plant_equipment_net": "Property, plant & equipment, net (PP&E net).",
    "goodwill": "Goodwill.",
    "intangible_assets": "Intangible assets, net (excluding goodwill).",
    "long_term_investments": "Long-term investments.",
    "other_non_current_assets": "Other non-current / long-term assets.",
    "total_non_current_assets": "Total non-current / long-term assets (reported subtotal).",
    "total_assets": "Total assets (the reported grand total).",
    # --- balance sheet: liabilities ---
    "accounts_payable": "Accounts payable / trade payables.",
    "short_term_debt": "Short-term debt / current portion of long-term debt / current borrowings.",
    "accrued_liabilities": "Accrued liabilities / accrued expenses.",
    "deferred_revenue_current": "Deferred revenue / unearned revenue (current portion).",
    "other_current_liabilities": "Other current liabilities.",
    "total_current_liabilities": "Total current liabilities (the reported subtotal).",
    "long_term_debt": "Long-term debt / non-current borrowings (excluding current portion).",
    "deferred_tax_liabilities": "Deferred tax liabilities.",
    "other_non_current_liabilities": "Other non-current / long-term liabilities.",
    "total_non_current_liabilities": "Total non-current / long-term liabilities (reported subtotal).",
    "total_liabilities": "Total liabilities (the reported total).",
    # --- balance sheet: equity ---
    "common_stock": "Common stock / share capital / paid-in capital.",
    "retained_earnings": "Retained earnings / accumulated deficit (negative if a deficit).",
    "treasury_stock": "Treasury stock (usually reported as a negative number).",
    "total_equity": "Total shareholders'/stockholders' equity (attributable to the company).",
    "minority_interest": "Minority / non-controlling interest.",
    # --- cash flow ---
    "operating_cash_flow": "Net cash provided by operating activities.",
    "depreciation_amortization_cf": "Depreciation & amortization add-back in the cash flow statement.",
    "stock_based_compensation": "Stock-based / share-based compensation add-back.",
    "change_in_working_capital": "Net change in operating working capital (sum of working-capital lines if reported).",
    "capital_expenditures": "Capital expenditures / purchases of PP&E. Store the sign AS REPORTED (usually negative).",
    "acquisitions": "Cash used for acquisitions, net of cash acquired.",
    "investing_cash_flow": "Net cash used in / provided by investing activities.",
    "debt_issued": "Proceeds from issuance of debt / borrowings.",
    "debt_repaid": "Repayments of debt. Store the sign AS REPORTED (usually negative).",
    "dividends_paid": "Dividends paid. Store the sign AS REPORTED (usually negative).",
    "share_repurchases": "Repurchases of common stock / buybacks. Store the sign AS REPORTED.",
    "financing_cash_flow": "Net cash used in / provided by financing activities.",
    "free_cash_flow": "Free cash flow only if explicitly reported; do NOT compute it.",
    "net_change_in_cash": "Net increase/decrease in cash and cash equivalents for the period.",
}


def _item_object_schema(field_description: str) -> dict[str, Any]:
    """Schema for a single extracted line item (value + provenance)."""
    return {
        "type": "object",
        "additionalProperties": False,
        "description": field_description,
        "properties": {
            "value": {
                "type": ["number", "null"],
                "description": (
                    "The figure in ACTUAL reporting-currency units (de-scaled: if the "
                    "statement says 'in thousands', multiply by 1000). null if this line "
                    "item is not reported on the document. Never compute or derive it."
                ),
            },
            "source_page": {
                "type": ["integer", "null"],
                "description": "1-based page number the value was read from, or null.",
            },
            "source_label": {
                "type": ["string", "null"],
                "description": "The VERBATIM row label seen on the document, or null.",
            },
            "confidence": {
                "type": ["number", "null"],
                "minimum": 0.0,
                "maximum": 1.0,
                "description": "Your confidence 0..1 that this mapping/value is correct.",
            },
        },
        "required": ["value", "source_page", "source_label", "confidence"],
    }


def build_extraction_schema() -> dict[str, Any]:
    """Build the JSON schema describing the object the LLM must return.

    The returned dict is a JSON Schema (draft-2020 compatible subset) with:
      * top-level statement metadata (company, currency, period, scale note, ...)
      * ``detected_statement_types``: which statements the document contains
      * ``items``: an object whose keys are EXACTLY the canonical field names, each an
        item object ``{value, source_page, source_label, confidence}``.
    """
    # Build the per-item property map dynamically so the canonical keys always come
    # straight from the shared contract.
    item_properties: dict[str, dict[str, Any]] = {}
    for key in ALL_CANONICAL_FIELDS:
        description = _FIELD_DESCRIPTIONS.get(
            key,
            f"Canonical line item '{key}'. Map the matching reported row to this key.",
        )
        item_properties[key] = _item_object_schema(description)

    return {
        "type": "object",
        "additionalProperties": False,
        "description": (
            "Structured extraction of a single company-period financial statement. "
            "Extract ONLY figures actually reported on the document; never compute, "
            "derive, or infer subtotals, totals, or ratios."
        ),
        "properties": {
            "company_name": {
                "type": ["string", "null"],
                "description": "Reporting company / entity name, or null if not shown.",
            },
            "ticker": {
                "type": ["string", "null"],
                "description": "Stock ticker symbol if shown, else null.",
            },
            "currency": {
                "type": ["string", "null"],
                "description": "ISO 4217 reporting currency code, e.g. 'USD', 'EUR'.",
            },
            "period_type": {
                "type": ["string", "null"],
                "enum": ["FY", "Q", "H", "TTM", None],
                "description": (
                    "Reporting period type: 'FY' (full fiscal year), 'Q' (quarter), "
                    "'H' (half year), or 'TTM' (trailing twelve months)."
                ),
            },
            "fiscal_year": {
                "type": ["integer", "null"],
                "description": "Fiscal year the figures pertain to, e.g. 2023.",
            },
            "fiscal_period_end": {
                "type": ["string", "null"],
                "description": "Period end date as ISO 'YYYY-MM-DD', or null.",
            },
            "units_scale_note": {
                "type": ["string", "null"],
                "description": (
                    "The scale the source reported figures in, verbatim, e.g. "
                    "'in thousands' or 'in millions, except per-share data'. Record this "
                    "even though the 'value' fields are already de-scaled to actual units."
                ),
            },
            "detected_statement_types": {
                "type": "array",
                "description": "Which financial statements this document contains.",
                "items": {
                    "type": "string",
                    "enum": ["income_statement", "balance_sheet", "cash_flow"],
                },
            },
            "items": {
                "type": "object",
                "additionalProperties": False,
                "description": (
                    "Canonical line items. Include a key only when its meaning matches a "
                    "reported row; leave unreported items as value=null."
                ),
                "properties": item_properties,
            },
        },
        "required": [
            "company_name",
            "ticker",
            "currency",
            "period_type",
            "fiscal_year",
            "fiscal_period_end",
            "units_scale_note",
            "detected_statement_types",
            "items",
        ],
    }


# Re-export the field groups so prompt builders can show the model the canonical
# vocabulary grouped by statement without re-importing from the schema module.
__all__ = [
    "build_extraction_schema",
    "INCOME_STATEMENT_FIELDS",
    "BALANCE_SHEET_FIELDS",
    "CASH_FLOW_FIELDS",
    "ALL_CANONICAL_FIELDS",
]
