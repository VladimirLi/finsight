"""Tests for the deterministic ratio engine.

These tests rely ONLY on pydantic (via app.schemas) and the pure-Python ratio
engine — no network, no OCR, no LLM, no heavy third-party SDKs. They verify:

* representative ratio values are numerically correct (hand-computed in the test),
* a missing required input yields status="unavailable" with the exact missing keys,
* a zero denominator yields status="undefined",
* percent-unit ratios are scaled to the 0..100 range as declared in definitions.py,
* market-dependent valuation ratios behave correctly with and without market data,
* documented sign conventions (capex negative, dividends negative) hold.
"""

from __future__ import annotations

import math

import pytest
from app.ratios.base import RatioCategory, RatioResult, RatioStatus
from app.ratios.definitions import RATIO_DEFINITIONS
from app.ratios.engine import compute_all_ratios, grouped_by_category
from app.schemas.financials import FinancialStatement, FinancialValue

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


def make_statement(**values: float) -> FinancialStatement:
    """Build a FinancialStatement from {canonical_key: numeric_value}."""
    return FinancialStatement(items={key: FinancialValue(value=val) for key, val in values.items()})


@pytest.fixture
def full_statement() -> FinancialStatement:
    """A complete, internally-consistent statement covering all ratios.

    Numbers are chosen to make hand-computation easy.
    """
    return make_statement(
        # income statement
        revenue=1000.0,
        cost_of_goods_sold=600.0,
        gross_profit=400.0,
        operating_income=200.0,
        interest_expense=40.0,
        net_income=120.0,
        ebitda=260.0,
        shares_outstanding_diluted=100.0,
        # balance sheet
        cash_and_equivalents=150.0,
        short_term_investments=50.0,
        accounts_receivable=100.0,
        inventory=200.0,
        total_current_assets=500.0,
        total_assets=2000.0,
        total_current_liabilities=250.0,
        long_term_debt=600.0,
        total_liabilities=900.0,
        total_equity=1100.0,
        # cash flow (capex & dividends stored as reported -> negative)
        operating_cash_flow=300.0,
        capital_expenditures=-80.0,
        dividends_paid=-60.0,
    )


def result_by_key(results: list[RatioResult], key: str) -> RatioResult:
    for r in results:
        if r.key == key:
            return r
    raise AssertionError(f"ratio {key!r} not found in results")


# ---------------------------------------------------------------------------
# Catalogue integrity
# ---------------------------------------------------------------------------


def test_definition_keys_are_unique():
    keys = [d.key for d in RATIO_DEFINITIONS]
    assert len(keys) == len(set(keys)), "duplicate ratio keys in catalogue"


def test_compute_all_ratios_returns_one_result_per_definition():
    results = compute_all_ratios(make_statement())
    assert len(results) == len(RATIO_DEFINITIONS)
    assert [r.key for r in results] == [d.key for d in RATIO_DEFINITIONS]


def test_units_are_from_allowed_set():
    allowed = {"ratio", "percent", "days", "currency", "x"}
    for d in RATIO_DEFINITIONS:
        assert d.unit in allowed, f"{d.key} has bad unit {d.unit}"


# ---------------------------------------------------------------------------
# Liquidity
# ---------------------------------------------------------------------------


def test_current_ratio(full_statement):
    r = result_by_key(compute_all_ratios(full_statement), "current_ratio")
    assert r.status is RatioStatus.ok
    # 500 / 250 = 2.0
    assert r.value == pytest.approx(2.0)
    assert r.unit == "ratio"


def test_quick_ratio(full_statement):
    r = result_by_key(compute_all_ratios(full_statement), "quick_ratio")
    # (150 + 50 + 100) / 250 = 1.2
    assert r.value == pytest.approx(1.2)


def test_cash_ratio(full_statement):
    r = result_by_key(compute_all_ratios(full_statement), "cash_ratio")
    # (150 + 50) / 250 = 0.8
    assert r.value == pytest.approx(0.8)


def test_working_capital(full_statement):
    r = result_by_key(compute_all_ratios(full_statement), "working_capital")
    # 500 - 250 = 250
    assert r.value == pytest.approx(250.0)
    assert r.unit == "currency"


# ---------------------------------------------------------------------------
# Leverage
# ---------------------------------------------------------------------------


def test_debt_to_equity(full_statement):
    r = result_by_key(compute_all_ratios(full_statement), "debt_to_equity")
    # 900 / 1100
    assert r.value == pytest.approx(900.0 / 1100.0)


def test_debt_ratio(full_statement):
    r = result_by_key(compute_all_ratios(full_statement), "debt_ratio")
    # 900 / 2000 = 0.45
    assert r.value == pytest.approx(0.45)


def test_equity_ratio(full_statement):
    r = result_by_key(compute_all_ratios(full_statement), "equity_ratio")
    # 1100 / 2000 = 0.55
    assert r.value == pytest.approx(0.55)


def test_long_term_debt_to_equity(full_statement):
    r = result_by_key(compute_all_ratios(full_statement), "long_term_debt_to_equity")
    # 600 / 1100
    assert r.value == pytest.approx(600.0 / 1100.0)


def test_interest_coverage(full_statement):
    r = result_by_key(compute_all_ratios(full_statement), "interest_coverage")
    # 200 / 40 = 5.0
    assert r.value == pytest.approx(5.0)
    assert r.unit == "x"


# ---------------------------------------------------------------------------
# Profitability (percent, scaled to 0..100)
# ---------------------------------------------------------------------------


def test_gross_margin_scaled_to_percent(full_statement):
    r = result_by_key(compute_all_ratios(full_statement), "gross_margin")
    # 400 / 1000 * 100 = 40.0  (NOT 0.4)
    assert r.value == pytest.approx(40.0)
    assert r.unit == "percent"
    assert 0.0 <= r.value <= 100.0


def test_operating_margin(full_statement):
    r = result_by_key(compute_all_ratios(full_statement), "operating_margin")
    # 200 / 1000 * 100 = 20.0
    assert r.value == pytest.approx(20.0)


def test_net_margin(full_statement):
    r = result_by_key(compute_all_ratios(full_statement), "net_margin")
    # 120 / 1000 * 100 = 12.0
    assert r.value == pytest.approx(12.0)


def test_return_on_assets(full_statement):
    r = result_by_key(compute_all_ratios(full_statement), "return_on_assets")
    # 120 / 2000 * 100 = 6.0
    assert r.value == pytest.approx(6.0)


def test_return_on_equity(full_statement):
    r = result_by_key(compute_all_ratios(full_statement), "return_on_equity")
    # 120 / 1100 * 100
    assert r.value == pytest.approx(120.0 / 1100.0 * 100.0)


def test_return_on_invested_capital(full_statement):
    r = result_by_key(compute_all_ratios(full_statement), "return_on_invested_capital")
    # 200 / (600 + 1100) * 100
    assert r.value == pytest.approx(200.0 / 1700.0 * 100.0)
    assert r.unit == "percent"


def test_ebitda_margin(full_statement):
    r = result_by_key(compute_all_ratios(full_statement), "ebitda_margin")
    # 260 / 1000 * 100 = 26.0
    assert r.value == pytest.approx(26.0)


# ---------------------------------------------------------------------------
# Efficiency
# ---------------------------------------------------------------------------


def test_asset_turnover(full_statement):
    r = result_by_key(compute_all_ratios(full_statement), "asset_turnover")
    # 1000 / 2000 = 0.5
    assert r.value == pytest.approx(0.5)


def test_inventory_turnover(full_statement):
    r = result_by_key(compute_all_ratios(full_statement), "inventory_turnover")
    # 600 / 200 = 3.0
    assert r.value == pytest.approx(3.0)


def test_receivables_turnover(full_statement):
    r = result_by_key(compute_all_ratios(full_statement), "receivables_turnover")
    # 1000 / 100 = 10.0
    assert r.value == pytest.approx(10.0)


def test_days_sales_outstanding(full_statement):
    r = result_by_key(compute_all_ratios(full_statement), "days_sales_outstanding")
    # 365 / (1000/100) = 36.5
    assert r.value == pytest.approx(36.5)
    assert r.unit == "days"


def test_days_inventory_outstanding(full_statement):
    r = result_by_key(compute_all_ratios(full_statement), "days_inventory_outstanding")
    # 365 / (600/200) = 365 / 3
    assert r.value == pytest.approx(365.0 / 3.0)


# ---------------------------------------------------------------------------
# Cash flow (sign conventions)
# ---------------------------------------------------------------------------


def test_operating_cash_flow_ratio(full_statement):
    r = result_by_key(compute_all_ratios(full_statement), "operating_cash_flow_ratio")
    # 300 / 250 = 1.2
    assert r.value == pytest.approx(1.2)


def test_free_cash_flow_adds_negative_capex(full_statement):
    r = result_by_key(compute_all_ratios(full_statement), "free_cash_flow")
    # 300 + (-80) = 220  (capex stored as reported negative -> added)
    assert r.value == pytest.approx(220.0)
    assert r.unit == "currency"


def test_fcf_margin(full_statement):
    r = result_by_key(compute_all_ratios(full_statement), "fcf_margin")
    # (300 - 80) / 1000 * 100 = 22.0
    assert r.value == pytest.approx(22.0)


def test_capex_to_revenue_uses_magnitude(full_statement):
    r = result_by_key(compute_all_ratios(full_statement), "capex_to_revenue")
    # |−80| / 1000 * 100 = 8.0  (positive intensity)
    assert r.value == pytest.approx(8.0)


# ---------------------------------------------------------------------------
# Per-share / valuation
# ---------------------------------------------------------------------------


def test_eps(full_statement):
    r = result_by_key(compute_all_ratios(full_statement), "eps")
    # 120 / 100 = 1.2
    assert r.value == pytest.approx(1.2)
    assert r.unit == "currency"


def test_book_value_per_share(full_statement):
    r = result_by_key(compute_all_ratios(full_statement), "book_value_per_share")
    # 1100 / 100 = 11.0
    assert r.value == pytest.approx(11.0)


def test_dividend_payout_ratio_uses_magnitude(full_statement):
    r = result_by_key(compute_all_ratios(full_statement), "dividend_payout_ratio")
    # |−60| / 120 * 100 = 50.0
    assert r.value == pytest.approx(50.0)


def test_pe_ratio_with_market_data(full_statement):
    results = compute_all_ratios(full_statement, market_data={"market_price": 24.0})
    r = result_by_key(results, "pe_ratio")
    # eps = 1.2 ; 24 / 1.2 = 20.0
    assert r.status is RatioStatus.ok
    assert r.value == pytest.approx(20.0)
    assert r.unit == "x"


def test_pb_ratio_with_market_data(full_statement):
    results = compute_all_ratios(full_statement, market_data={"market_price": 22.0})
    r = result_by_key(results, "pb_ratio")
    # bvps = 11.0 ; 22 / 11 = 2.0
    assert r.value == pytest.approx(2.0)


def test_valuation_ratio_unavailable_without_market_data(full_statement):
    # No market_data passed -> market_price is missing.
    r = result_by_key(compute_all_ratios(full_statement), "pe_ratio")
    assert r.status is RatioStatus.unavailable
    assert r.missing_inputs == ["market_price"]


# ---------------------------------------------------------------------------
# Missing-input handling
# ---------------------------------------------------------------------------


def test_missing_single_input_marks_unavailable():
    # Provide current assets but omit current liabilities.
    stmt = make_statement(total_current_assets=500.0)
    r = result_by_key(compute_all_ratios(stmt), "current_ratio")
    assert r.status is RatioStatus.unavailable
    assert r.missing_inputs == ["total_current_liabilities"]
    assert r.value is None


def test_missing_multiple_inputs_lists_all():
    # Quick ratio needs four inputs; provide only one.
    stmt = make_statement(cash_and_equivalents=100.0)
    r = result_by_key(compute_all_ratios(stmt), "quick_ratio")
    assert r.status is RatioStatus.unavailable
    assert r.missing_inputs == [
        "short_term_investments",
        "accounts_receivable",
        "total_current_liabilities",
    ]


def test_empty_statement_makes_everything_unavailable():
    results = compute_all_ratios(make_statement())
    assert all(r.status is RatioStatus.unavailable for r in results)
    assert all(r.value is None for r in results)


# ---------------------------------------------------------------------------
# Undefined (zero denominator)
# ---------------------------------------------------------------------------


def test_zero_denominator_marks_undefined():
    stmt = make_statement(total_current_assets=500.0, total_current_liabilities=0.0)
    r = result_by_key(compute_all_ratios(stmt), "current_ratio")
    assert r.status is RatioStatus.undefined
    assert r.value is None


def test_zero_revenue_marks_margin_undefined():
    stmt = make_statement(gross_profit=400.0, revenue=0.0)
    r = result_by_key(compute_all_ratios(stmt), "gross_margin")
    assert r.status is RatioStatus.undefined


def test_zero_eps_makes_pe_undefined():
    # net_income = 0 -> eps = 0 -> price/eps divides by zero.
    stmt = make_statement(net_income=0.0, shares_outstanding_diluted=100.0)
    results = compute_all_ratios(stmt, market_data={"market_price": 10.0})
    r = result_by_key(results, "pe_ratio")
    assert r.status is RatioStatus.undefined


# ---------------------------------------------------------------------------
# Percent scaling invariant across all percent ratios
# ---------------------------------------------------------------------------


def test_all_percent_ratios_scaled_to_hundred(full_statement):
    results = compute_all_ratios(full_statement, market_data={"market_price": 20.0})
    for r in results:
        if r.unit == "percent" and r.status is RatioStatus.ok:
            # Hand-built fixture keeps every percent metric within a sane 0..100 band.
            assert 0.0 <= r.value <= 100.0, f"{r.key} not scaled to percent: {r.value}"


# ---------------------------------------------------------------------------
# Grouping helper
# ---------------------------------------------------------------------------


def test_grouped_by_category(full_statement):
    results = compute_all_ratios(full_statement, market_data={"market_price": 20.0})
    grouped = grouped_by_category(results)

    # Every group key is a valid category value.
    valid = {c.value for c in RatioCategory}
    assert set(grouped).issubset(valid)

    # No result is lost or duplicated by grouping.
    total = sum(len(v) for v in grouped.values())
    assert total == len(results)

    # Sanity: known ratios land in the expected categories.
    assert any(r.key == "current_ratio" for r in grouped["liquidity"])
    assert any(r.key == "pe_ratio" for r in grouped["valuation"])


def test_results_are_finite_when_ok(full_statement):
    results = compute_all_ratios(full_statement, market_data={"market_price": 20.0})
    for r in results:
        if r.status is RatioStatus.ok:
            assert math.isfinite(r.value), f"{r.key} produced non-finite value"
