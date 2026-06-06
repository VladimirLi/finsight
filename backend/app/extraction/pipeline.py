"""Extraction pipeline: ParsedDocument -> FinancialStatement.

Orchestrates the LLM extraction:

    1. Build the JSON schema (the canonical target shape).
    2. Build the system + user prompts from the parsed document.
    3. Call ``provider.extract_json(...)`` to get structured JSON.
    4. Validate / coerce that JSON into a :class:`FinancialStatement`, dropping unknown
       keys, building a :class:`FinancialValue` per reported item, and applying minimal,
       well-commented, deterministic normalization (numeric-string coercion,
       parentheses-negative handling) for anything that slips past the model.

Design notes
------------
* No derivation. We never compute subtotals, totals, or ratios here — that is the ratio
  engine's deterministic job. We only transcribe and clean what the model returned.
* Robust on partial data. Malformed individual items are skipped rather than aborting the
  whole extraction; the worst case is fewer populated line items, never a crash.
* The only hard failure path is when the provider itself cannot return parseable JSON
  (it raises ``LLMError``), which we let propagate to the caller.
"""

from __future__ import annotations

import re
from typing import Any

from app.extraction.prompts import build_system_prompt, build_user_prompt
from app.extraction.schema import build_extraction_schema
from app.llm.base import LLMError, LLMProvider
from app.ocr.base import ParsedDocument
from app.schemas.financials import (
    ALL_CANONICAL_FIELDS,
    BALANCE_SHEET_FIELDS,
    CASH_FLOW_FIELDS,
    INCOME_STATEMENT_FIELDS,
    FinancialStatement,
    FinancialValue,
    PeriodType,
)

# Canonical keys as a set for O(1) membership checks when dropping unknown keys.
_CANONICAL_SET = set(ALL_CANONICAL_FIELDS)

# Valid period_type enum values (string side of the PeriodType enum).
_VALID_PERIOD_TYPES = {pt.value for pt in PeriodType}

# Matches a number that may use thousands separators and/or a decimal part, optionally
# wrapped in parentheses (accounting negative) or prefixed with a currency symbol / sign.
_NUMERIC_RE = re.compile(
    r"""^\s*
        (?P<paren>\()?            # optional opening paren (accounting negative)
        \s*[-+]?\s*               # optional explicit sign
        [^\d().-]*                # optional leading currency symbol / spaces
        (?P<num>\d[\d,\s]*(?:\.\d+)?)
        \s*%?                     # tolerate a trailing percent sign (stripped)
        \s*\)?                    # optional closing paren
        \s*$""",
    re.VERBOSE,
)


def _coerce_number(raw: Any) -> float | None:
    """Best-effort coercion of a model-returned value to ``float``.

    Handles the cases that occasionally slip past schema constraints:
      * already-numeric ints/floats -> returned as float
      * numeric strings with commas / spaces / currency symbols -> parsed
      * parentheses-wrapped strings '(1,234)' -> negative
      * empty / 'null' / '-' / 'n/a' placeholders -> None
    Returns ``None`` for anything that is not a usable number.
    """
    if raw is None:
        return None
    if isinstance(raw, bool):  # guard: bool is a subclass of int, never a figure
        return None
    if isinstance(raw, (int, float)):
        return float(raw)
    if not isinstance(raw, str):
        return None

    s = raw.strip()
    if not s:
        return None
    if s.lower() in {"null", "none", "n/a", "na", "-", "—", "--"}:
        return None

    m = _NUMERIC_RE.match(s)
    if not m:
        return None

    digits = m.group("num").replace(",", "").replace(" ", "")
    try:
        value = float(digits)
    except ValueError:
        return None

    # Apply accounting-negative if the original was wrapped in parentheses, or carried
    # an explicit leading minus sign.
    if m.group("paren") or s.lstrip().startswith("-"):
        value = -abs(value)
    return value


def _coerce_int(raw: Any) -> int | None:
    """Coerce a value to int (used for source_page, fiscal_year)."""
    num = _coerce_number(raw)
    if num is None:
        return None
    try:
        return int(round(num))
    except (ValueError, OverflowError):
        return None


def _coerce_confidence(raw: Any) -> float | None:
    """Coerce/clamp a confidence into [0, 1], or None."""
    num = _coerce_number(raw)
    if num is None:
        return None
    if num < 0.0:
        return 0.0
    if num > 1.0:
        # Models sometimes emit confidence on a 0..100 scale; rescale to 0..1.
        return min(num / 100.0, 1.0)
    return num


def _coerce_str(raw: Any) -> str | None:
    """Coerce to a non-empty trimmed string, or None."""
    if raw is None:
        return None
    if not isinstance(raw, str):
        raw = str(raw)
    s = raw.strip()
    return s or None


def _build_financial_value(item: Any) -> FinancialValue | None:
    """Build a :class:`FinancialValue` from one model item object.

    Accepts either the structured ``{value, source_page, source_label, confidence}``
    object the schema asks for, or a bare scalar (some models shortcut to just the
    number). Returns ``None`` when there is no usable value, so the caller can skip
    storing an empty placeholder.
    """
    # Bare scalar shortcut: treat as the value with no provenance.
    if not isinstance(item, dict):
        value = _coerce_number(item)
        if value is None:
            return None
        return FinancialValue(value=value)

    value = _coerce_number(item.get("value"))
    if value is None:
        # No reported figure -> don't store an empty item (keeps `present()` honest).
        return None

    return FinancialValue(
        value=value,
        source_page=_coerce_int(item.get("source_page")),
        source_label=_coerce_str(item.get("source_label")),
        confidence=_coerce_confidence(item.get("confidence")),
    )


def _coerce_period_type(raw: Any) -> PeriodType | None:
    """Map a model period_type string to the :class:`PeriodType` enum, or None."""
    s = _coerce_str(raw)
    if s is None:
        return None
    s_up = s.upper()
    if s_up in _VALID_PERIOD_TYPES:
        return PeriodType(s_up)
    # Tolerate a few common spellings the model might emit.
    aliases = {
        "ANNUAL": PeriodType.fiscal_year,
        "YEAR": PeriodType.fiscal_year,
        "FULL YEAR": PeriodType.fiscal_year,
        "QUARTER": PeriodType.quarter,
        "QUARTERLY": PeriodType.quarter,
        "HALF": PeriodType.half_year,
        "HALF YEAR": PeriodType.half_year,
        "SEMIANNUAL": PeriodType.half_year,
        "TRAILING TWELVE MONTHS": PeriodType.ttm,
    }
    return aliases.get(s_up)


def _coerce_currency(raw: Any) -> str | None:
    """Normalize a currency to a 3-letter ISO-ish code where obvious."""
    s = _coerce_str(raw)
    if s is None:
        return None
    s = s.strip().upper()
    # Map a few common symbols/words; otherwise pass through (e.g. already 'USD').
    symbol_map = {
        "$": "USD",
        "US$": "USD",
        "USD": "USD",
        "€": "EUR",
        "EUR": "EUR",
        "£": "GBP",
        "GBP": "GBP",
        "¥": "JPY",
        "JPY": "JPY",
        "DOLLARS": "USD",
        "EUROS": "EUR",
    }
    return symbol_map.get(s, s)


def extract_statement(
    doc: ParsedDocument,
    provider: LLMProvider,
    model: str,
) -> FinancialStatement:
    """Extract a :class:`FinancialStatement` from a parsed document via an LLM.

    Parameters
    ----------
    doc:
        The OCR/parse result (page text + tables).
    provider:
        Any :class:`LLMProvider` implementation (Anthropic/OpenAI/Ollama/...).
    model:
        The provider-specific model id to use.

    Returns:
    -------
    FinancialStatement
        Populated with whatever the model reliably reported. Unreported items are simply
        absent from ``items`` (``statement.get(key)`` returns ``None`` for them).

    Raises:
    ------
    LLMError
        Only if the provider cannot produce parseable JSON at all.
    """
    schema = build_extraction_schema()
    system = build_system_prompt()
    prompt = build_user_prompt(doc)

    response = provider.extract_json(
        system=system,
        prompt=prompt,
        json_schema=schema,
        model=model,
    )

    # The provider contract guarantees `parsed` is populated on success; defend anyway.
    parsed = response.parsed
    if not isinstance(parsed, dict):
        raise LLMError("LLM did not return a JSON object for extraction.")

    return _coerce_to_statement(parsed, doc)


def _coerce_to_statement(
    parsed: dict[str, Any],
    doc: ParsedDocument,
) -> FinancialStatement:
    """Validate/coerce a parsed JSON dict into a :class:`FinancialStatement`.

    Unknown keys are dropped; only canonical line items with a usable numeric value are
    stored. This is intentionally forgiving: a malformed individual item is skipped, not
    fatal, so partial extractions still yield a usable statement.
    """
    # ----- statement-level metadata -----
    company_name = _coerce_str(parsed.get("company_name"))
    ticker = _coerce_str(parsed.get("ticker"))
    ticker = ticker.upper() if ticker else None
    currency = _coerce_currency(parsed.get("currency"))
    period_type = _coerce_period_type(parsed.get("period_type"))
    fiscal_year = _coerce_int(parsed.get("fiscal_year"))
    fiscal_period_end = _coerce_str(parsed.get("fiscal_period_end"))
    units_scale_note = _coerce_str(parsed.get("units_scale_note"))

    # ----- line items: keep only canonical keys with a usable value -----
    raw_items = parsed.get("items")
    items: dict[str, FinancialValue] = {}
    if isinstance(raw_items, dict):
        for key, raw_value in raw_items.items():
            if key not in _CANONICAL_SET:
                continue  # drop unknown keys silently
            fv = _build_financial_value(raw_value)
            if fv is not None:
                items[key] = fv

    statement = FinancialStatement(
        company_name=company_name,
        ticker=ticker,
        currency=currency,
        period_type=period_type,
        fiscal_year=fiscal_year,
        fiscal_period_end=fiscal_period_end,
        units_scale_note=units_scale_note,
        items=items,
    )
    return statement


# ---------------------------------------------------------------------------
# Optional heuristic helper. The authoritative statement-type detection comes from the
# LLM (detected_statement_types), but this keyword heuristic is useful for quick routing
# / logging without a model call, and for tests.
# ---------------------------------------------------------------------------

# Distinctive phrases that strongly indicate each statement type. Kept lowercase.
_STATEMENT_SIGNALS: dict[str, tuple[str, ...]] = {
    "income_statement": (
        "income statement",
        "statement of operations",
        "statement of income",
        "profit and loss",
        "statement of comprehensive income",
        "net sales",
        "cost of goods sold",
        "cost of sales",
        "operating income",
        "earnings per share",
        "net income",
    ),
    "balance_sheet": (
        "balance sheet",
        "statement of financial position",
        "total current assets",
        "total assets",
        "total liabilities",
        "shareholders' equity",
        "stockholders' equity",
        "retained earnings",
    ),
    "cash_flow": (
        "cash flow",
        "statement of cash flows",
        "operating activities",
        "investing activities",
        "financing activities",
        "net cash provided by",
        "net cash used in",
    ),
}


def detect_statement_types(doc: ParsedDocument) -> list[str]:
    """Heuristically guess which statement types a document contains.

    Returns a list drawn from {"income_statement", "balance_sheet", "cash_flow"} for
    every type whose distinctive phrases appear in the document text or tables. This is a
    lightweight convenience; the LLM's ``detected_statement_types`` is authoritative.
    """
    # Concatenate page text and table markdown, lowercased, for keyword scanning.
    haystack_parts: list[str] = [p.text for p in doc.pages if p.text]
    for page in doc.pages:
        for table in page.tables:
            haystack_parts.append(table.to_markdown())
    haystack = "\n".join(haystack_parts).lower()

    detected: list[str] = []
    for stmt_type, signals in _STATEMENT_SIGNALS.items():
        # Require at least two distinct signal phrases to reduce false positives from a
        # stray mention (e.g. a single "net income" reference in MD&A prose).
        hits = sum(1 for phrase in signals if phrase in haystack)
        if hits >= 2:
            detected.append(stmt_type)
    return detected


__all__ = [
    "extract_statement",
    "detect_statement_types",
]


# Reference the imported field groups so static analyzers see they are part of the
# module's public surface (they document the canonical grouping for callers/tests).
_FIELD_GROUPS = (INCOME_STATEMENT_FIELDS, BALANCE_SHEET_FIELDS, CASH_FLOW_FIELDS)
