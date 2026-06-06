"""Tests for strict Pydantic validation on the canonical financial models.

Verifies that:
  (a) FinancialValue rejects string-typed numbers directly (strict=True),
  (b) the pipeline's _coerce_number helper converts strings to float before
      model construction,
  (c) a full model_dump(mode="json") → model_validate round-trip succeeds
      under strict mode (this is the path used by the DB layer in service.py).
"""

from __future__ import annotations

import pytest
from app.extraction.pipeline import _build_financial_value, _coerce_number
from app.schemas.financials import FinancialStatement, FinancialValue
from pydantic import ValidationError

# ---------------------------------------------------------------------------
# (a) strict mode rejects string numbers on FinancialValue
# ---------------------------------------------------------------------------


def test_financial_value_rejects_string_number() -> None:
    """Passing a string like '1,234' directly as value must raise ValidationError."""
    with pytest.raises(ValidationError):
        FinancialValue(value="1,234")  # type: ignore[arg-type]


def test_financial_value_rejects_string_float() -> None:
    """Any string value, even a bare digit string, must be rejected."""
    with pytest.raises(ValidationError):
        FinancialValue(value="1000")  # type: ignore[arg-type]


def test_financial_value_accepts_float() -> None:
    """A proper Python float must be accepted."""
    fv = FinancialValue(value=1234.0)
    assert fv.value == 1234.0


def test_financial_value_accepts_int() -> None:
    """Pydantic strict mode accepts int for a float field (int is a numeric type)."""
    fv = FinancialValue(value=1234)
    assert fv.value == 1234.0


def test_financial_value_accepts_none() -> None:
    """None must be accepted (value is optional)."""
    fv = FinancialValue(value=None)
    assert fv.value is None


# ---------------------------------------------------------------------------
# (b) pipeline coercion: string → float before model construction
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("1,234", 1234.0),
        ("1,234.56", 1234.56),
        ("(1,234)", -1234.0),
        ("-500", -500.0),
        ("1 000", 1000.0),
        ("$1,000.00", 1000.0),
        ("", None),
        ("-", None),
        ("N/A", None),
        ("n/a", None),
        ("null", None),
        (None, None),
        (42, 42.0),
        (3.14, 3.14),
        (True, None),  # bool guard
    ],
)
def test_coerce_number(raw: object, expected: float | None) -> None:
    assert _coerce_number(raw) == expected


def test_build_financial_value_coerces_string() -> None:
    """_build_financial_value with a string-valued dict must produce a FinancialValue."""
    item = {"value": "1,234", "source_page": 1, "source_label": "Revenue", "confidence": 0.9}
    fv = _build_financial_value(item)
    assert fv is not None
    assert fv.value == 1234.0
    assert fv.source_page == 1
    assert fv.source_label == "Revenue"
    assert fv.confidence == pytest.approx(0.9)


def test_build_financial_value_parens_negative() -> None:
    """Parentheses-wrapped accounting negatives must be coerced to negative float."""
    fv = _build_financial_value({"value": "(500)", "confidence": 0.8})
    assert fv is not None
    assert fv.value == -500.0


def test_build_financial_value_empty_returns_none() -> None:
    """An empty/null value must return None so the key is not stored."""
    assert _build_financial_value({"value": ""}) is None
    assert _build_financial_value({"value": None}) is None
    assert _build_financial_value({"value": "N/A"}) is None


# ---------------------------------------------------------------------------
# (c) round-trip: model_dump(mode="json") → model_validate
# ---------------------------------------------------------------------------


def _make_statement() -> FinancialStatement:
    """Build a realistic FinancialStatement with several line items."""
    return FinancialStatement(
        company_name="Acme Corp",
        ticker="ACME",
        currency="USD",
        fiscal_year=2023,
        items={
            "revenue": FinancialValue(
                value=1_000_000.0,
                source_page=3,
                source_label="Total Revenue",
                confidence=0.95,
            ),
            "net_income": FinancialValue(value=123_456.0, confidence=0.9),
            "capital_expenditures": FinancialValue(value=-50_000.0),
        },
    )


def test_round_trip_model_dump_validate() -> None:
    """model_dump(mode='json') → model_validate must succeed under strict mode.

    This mirrors what service.py does when storing to / loading from the DB.
    """
    original = _make_statement()
    dumped = original.model_dump(mode="json")

    # model_validate must not raise under strict=True
    restored = FinancialStatement.model_validate(dumped)

    assert restored.company_name == original.company_name
    assert restored.fiscal_year == original.fiscal_year
    assert restored.items["revenue"].value == pytest.approx(1_000_000.0)
    assert restored.items["revenue"].confidence == pytest.approx(0.95)
    assert restored.items["capital_expenditures"].value == pytest.approx(-50_000.0)


def test_round_trip_empty_statement() -> None:
    """An empty FinancialStatement must round-trip cleanly."""
    original = FinancialStatement()
    dumped = original.model_dump(mode="json")
    restored = FinancialStatement.model_validate(dumped)
    assert restored.items == {}
    assert restored.company_name is None
