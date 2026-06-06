"""Prompt builders for LLM-driven financial-statement extraction.

Two prompts are produced:

* :func:`build_system_prompt` – the model's persona and the hard rules that keep the
  extraction faithful: map synonyms to canonical keys, de-scale to actual units, cite
  sources, and NEVER compute or derive numbers (subtotals, totals, ratios). Derivation
  is the ratio engine's job and is done deterministically in Python.
* :func:`build_user_prompt` – the document itself: page-marked text plus tables rendered
  as markdown, followed by the canonical vocabulary (grouped by statement) the model must
  map onto.

Both return plain strings; the JSON *shape* is enforced separately via the schema from
:mod:`app.extraction.schema`, so these prompts focus on semantics, not structure.
"""

from __future__ import annotations

from app.extraction.schema import (
    BALANCE_SHEET_FIELDS,
    CASH_FLOW_FIELDS,
    INCOME_STATEMENT_FIELDS,
)
from app.ocr.base import ParsedDocument

# Guardrail: very large documents can blow past context windows. We cap the text and
# table payloads at generous-but-bounded sizes and note any truncation so the model
# knows it is not seeing the whole file (rather than silently inventing data).
_MAX_TEXT_CHARS = 120_000
_MAX_TABLES_CHARS = 80_000


def build_system_prompt() -> str:
    """Return the system prompt establishing the extractor's rules."""
    return (
        "You are a meticulous financial-data extraction engine. You read OCR'd text and "
        "tables from a company's financial statements (income statement, balance sheet, "
        "and/or cash flow statement) and return STRICT JSON matching the provided schema.\n"
        "\n"
        "Follow these rules exactly:\n"
        "1. EXTRACT ONLY REPORTED FIGURES. Transcribe numbers that actually appear on the "
        "document. If a line item is not reported, set its value to null. Never guess.\n"
        "2. NEVER COMPUTE OR DERIVE ANYTHING. Do not calculate subtotals, totals, gross "
        "profit, EBITDA, free cash flow, ratios, or any figure not printed on the page. "
        "If a subtotal (e.g. total_current_assets) is not printed, leave it null even if "
        "you could add it up. Derivation happens downstream, deterministically.\n"
        "3. DE-SCALE TO ACTUAL UNITS. Statements are often reported 'in thousands' or 'in "
        "millions'. Convert every value to actual currency units: multiply by 1,000 for "
        "thousands, by 1,000,000 for millions. Record the original scale verbatim in "
        "units_scale_note (e.g. 'in thousands'). EXCEPTIONS: per-share figures "
        "(eps_diluted) and share counts (shares_outstanding_*) are usually NOT scaled the "
        "same way — transcribe share counts in actual shares and EPS as the per-share "
        "amount printed; do not apply the statement's monetary scale to a per-share value.\n"
        "4. HANDLE NEGATIVES. Parentheses around a number mean it is negative, e.g. "
        "'(1,234)' = -1234. For naturally-signed cash-flow lines (capital_expenditures, "
        "debt_repaid, dividends_paid, share_repurchases) and treasury_stock, keep the sign "
        "AS REPORTED on the document. Report interest_expense as a positive magnitude.\n"
        "5. MAP SYNONYMS to the canonical keys using the field descriptions in the schema "
        "(e.g. 'Cost of sales' -> cost_of_goods_sold, 'Total current assets' -> "
        "total_current_assets, 'Net cash from operating activities' -> "
        "operating_cash_flow). Do not invent keys outside the schema.\n"
        "6. CITE SOURCES. For every non-null value, set source_page to the 1-based page it "
        "was read from and source_label to the VERBATIM row label seen on the document. "
        "Provide a confidence between 0 and 1.\n"
        "7. ONE COMPANY-PERIOD. If multiple periods/columns are shown, extract the most "
        "recent / primary reporting period (the latest fiscal year or quarter) and ignore "
        "comparative prior-period columns.\n"
        "8. Return ONLY the JSON object. No prose, no markdown, no commentary."
    )


def _format_canonical_vocabulary() -> str:
    """Render the canonical keys grouped by statement for the model to map onto."""
    lines = [
        "INCOME STATEMENT keys:",
        "  " + ", ".join(INCOME_STATEMENT_FIELDS),
        "",
        "BALANCE SHEET keys:",
        "  " + ", ".join(BALANCE_SHEET_FIELDS),
        "",
        "CASH FLOW keys:",
        "  " + ", ".join(CASH_FLOW_FIELDS),
    ]
    return "\n".join(lines)


def _truncate(text: str, limit: int, what: str) -> str:
    """Truncate ``text`` to ``limit`` chars, appending a visible marker if cut."""
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n\n[...{what} truncated at {limit} characters; remainder omitted...]"


def build_user_prompt(doc: ParsedDocument) -> str:
    """Return the user prompt containing the document text and tables.

    The text is page-marked (``[Page N]``) and the tables are rendered as markdown with
    their page markers, both supplied by :class:`ParsedDocument`'s helpers, so the model
    can cite ``source_page`` accurately.
    """
    full_text = _truncate(doc.full_text(), _MAX_TEXT_CHARS, "document text")
    tables_md = doc.all_tables_markdown()
    tables_section = (
        _truncate(tables_md, _MAX_TABLES_CHARS, "tables")
        if tables_md.strip()
        else "(no structured tables were recovered; rely on the text above)"
    )

    return (
        f"Document filename: {doc.filename}\n"
        f"Total pages: {doc.num_pages}\n"
        "\n"
        "Extract the financial statement into the required JSON schema. Use the page "
        "markers to fill source_page. Map each reported row to the matching canonical key "
        "listed at the bottom; leave unreported items null; never compute missing values.\n"
        "\n"
        "===== DOCUMENT TEXT (page-marked) =====\n"
        f"{full_text}\n"
        "\n"
        "===== EXTRACTED TABLES (markdown, page-marked) =====\n"
        f"{tables_section}\n"
        "\n"
        "===== CANONICAL KEYS TO MAP ONTO =====\n"
        f"{_format_canonical_vocabulary()}\n"
    )


__all__ = ["build_system_prompt", "build_user_prompt"]
