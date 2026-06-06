"""Deterministic tests for the parse -> extract path (no network, no real LLM).

Feeds :func:`app.extraction.pipeline.extract_statement` a hand-built
``ParsedDocument`` plus a :class:`FakeLLMProvider` whose JSON payload contains:

  * string numbers with thousands separators ("1,234"),
  * accounting-negative parentheses ("(500)"),
  * an "in thousands" scaling note,

and asserts the resulting :class:`FinancialStatement`:

  * coerces those strings to proper Python floats (strict pydantic accepts the
    pipeline output),
  * preserves provenance (source_page / source_label / confidence),
  * leaves unreported items absent so ``statement.get(key)`` returns ``None``,
  * carries the de-scaled (actual-unit) values the model is asked to emit, while
    retaining the human-readable ``units_scale_note`` for audit.
"""

from __future__ import annotations

from typing import Any

import pytest
from app.extraction.pipeline import extract_statement
from app.schemas.financials import (
    FinancialStatement,
    FinancialValue,
    PeriodType,
)

from tests.conftest import FakeLLMProvider, build_parsed_document


def _payload() -> dict[str, Any]:
    """Canned LLM JSON: messy string numbers + de-scaled actual-unit values.

    The source statement is "in thousands"; per the schema contract the model is
    asked to return values already de-scaled to actual currency units, so e.g. a
    reported "1,234" (thousands) comes back as 1,234,000. We exercise the
    pipeline's numeric-string / parentheses coercion on those de-scaled values.
    """
    return {
        "company_name": "Acme Corp",
        "ticker": "acme",  # lower-case on purpose: pipeline upper-cases it
        "currency": "$",  # symbol on purpose: pipeline maps to USD
        "period_type": "annual",  # alias on purpose: maps to FY
        "fiscal_year": "2023",
        "fiscal_period_end": "2023-12-31",
        "units_scale_note": "in thousands",
        "items": {
            # de-scaled actual units, supplied as a comma-grouped string
            "revenue": {
                "value": "1,234,000",
                "source_page": 3,
                "source_label": "Total net revenue",
                "confidence": 0.95,
            },
            # accounting-negative parentheses -> negative float
            "operating_expenses": {
                "value": "(500,000)",
                "source_page": 3,
                "source_label": "Operating expenses",
                "confidence": "0.9",
            },
            "net_income": {
                "value": "734,000",
                "source_page": 3,
                "source_label": "Net income",
                "confidence": 0.88,
            },
            # placeholder / unreported -> must be dropped, key stays absent
            "ebitda": {"value": "N/A"},
            # unknown / non-canonical key -> dropped silently
            "totally_made_up_field": {"value": "1"},
        },
    }


def _doc() -> Any:
    return build_parsed_document(
        filename="acme_10k.pdf",
        pages=[
            (
                "ACME CORP\nConsolidated Statement of Operations\n(in thousands)",
                [
                    ["Total net revenue", "1,234"],
                    ["Operating expenses", "(500)"],
                    ["Net income", "734"],
                ],
            ),
        ],
    )


@pytest.fixture
def statement() -> FinancialStatement:
    provider = FakeLLMProvider(_payload())
    return extract_statement(_doc(), provider, model="fake-model")


def test_output_is_strict_financial_statement(statement: FinancialStatement) -> None:
    """The pipeline output is a strict-pydantic FinancialStatement instance.

    The full surface — items, scalar metadata, AND the ``period_type`` enum —
    survives a ``model_dump(mode="json")`` -> ``model_validate`` round-trip, which
    is exactly what the DB persistence layer relies on.
    """
    assert isinstance(statement, FinancialStatement)
    dumped = statement.model_dump(mode="json")
    restored = FinancialStatement.model_validate(dumped)
    assert restored.get("revenue") == pytest.approx(1_234_000.0)
    assert restored.items["operating_expenses"].value == pytest.approx(-500_000.0)
    assert restored.period_type is statement.period_type


def test_strict_period_type_round_trips(statement: FinancialStatement) -> None:
    """Regression: a StrEnum period_type survives the strict JSON round-trip.

    ``model_dump(mode="json")`` serialises PeriodType.fiscal_year to the string
    "FY"; the field declares ``strict=False`` so ``model_validate`` coerces it back
    to the enum even though the model is otherwise strict. This is what makes
    ``app.extraction.service.get_statement()`` work for persisted periods.
    """
    assert statement.period_type is not None
    dumped = statement.model_dump(mode="json")
    assert dumped["period_type"] == "FY"
    restored = FinancialStatement.model_validate(dumped)
    assert restored.period_type is PeriodType.fiscal_year


def test_metadata_coerced(statement: FinancialStatement) -> None:
    assert statement.company_name == "Acme Corp"
    assert statement.ticker == "ACME"  # upper-cased
    assert statement.currency == "USD"  # symbol mapped
    assert statement.period_type == PeriodType.fiscal_year  # "annual" alias
    assert statement.fiscal_year == 2023  # string -> int
    assert statement.fiscal_period_end == "2023-12-31"
    assert statement.units_scale_note == "in thousands"


def test_string_numbers_coerced_to_float(statement: FinancialStatement) -> None:
    """Comma-grouped string numbers become proper Python floats."""
    revenue = statement.get("revenue")
    assert isinstance(revenue, float)
    assert revenue == pytest.approx(1_234_000.0)

    net_income = statement.get("net_income")
    assert net_income == pytest.approx(734_000.0)


def test_parentheses_negative(statement: FinancialStatement) -> None:
    """Accounting-negative parentheses coerce to a negative float."""
    opex = statement.get("operating_expenses")
    assert opex == pytest.approx(-500_000.0)


def test_descaled_values_not_in_thousands(statement: FinancialStatement) -> None:
    """Values are actual currency units, not the raw 'in thousands' figures."""
    # 1,234 thousand == 1,234,000 actual; ensure we did NOT store the raw 1234.
    assert statement.get("revenue") == pytest.approx(1_234_000.0)
    assert statement.get("revenue") != pytest.approx(1_234.0)


def test_provenance_preserved(statement: FinancialStatement) -> None:
    fv = statement.items["revenue"]
    assert isinstance(fv, FinancialValue)
    assert fv.source_page == 3
    assert fv.source_label == "Total net revenue"
    assert fv.confidence == pytest.approx(0.95)
    assert fv.edited_by_user is False


def test_string_confidence_coerced(statement: FinancialStatement) -> None:
    """A confidence supplied as a string is coerced into [0, 1]."""
    assert statement.items["operating_expenses"].confidence == pytest.approx(0.9)


def test_unreported_items_absent(statement: FinancialStatement) -> None:
    """Items with placeholder values (and unknown keys) are not stored."""
    # 'ebitda' had value "N/A" -> dropped.
    assert "ebitda" not in statement.items
    assert statement.get("ebitda") is None
    # A field never mentioned at all.
    assert statement.get("total_assets") is None


def test_unknown_keys_dropped(statement: FinancialStatement) -> None:
    """Non-canonical keys returned by the model are silently dropped."""
    assert "totally_made_up_field" not in statement.items


def test_only_reported_canonical_items_present(statement: FinancialStatement) -> None:
    assert set(statement.items) == {"revenue", "operating_expenses", "net_income"}


def test_bare_scalar_items_supported() -> None:
    """A model that shortcuts to bare scalar values (no provenance) still parses."""
    payload: dict[str, Any] = {
        "company_name": "Bare Co",
        "items": {
            "revenue": "2,000",  # bare string scalar
            "net_income": 500,  # bare numeric scalar
            "cost_of_goods_sold": None,  # explicit null -> dropped
        },
    }
    provider = FakeLLMProvider(payload)
    stmt = extract_statement(_doc(), provider, model="fake-model")
    assert stmt.get("revenue") == pytest.approx(2_000.0)
    assert stmt.get("net_income") == pytest.approx(500.0)
    assert "cost_of_goods_sold" not in stmt.items
    # Bare scalars carry no provenance.
    assert stmt.items["revenue"].source_page is None
