"""Tests for the deterministic accounting-identity validation layer.

Covers the four contracted behaviours:
    (a) a balanced statement -> every checkable identity is ``ok``;
    (b) an unbalanced statement -> ``mismatch`` with the correct signed difference;
    (c) missing inputs -> ``unavailable`` listing exactly the missing keys;
    (d) tiny rounding noise is absorbed by the default relative tolerance.
"""

from __future__ import annotations

from app.schemas.financials import FinancialStatement, FinancialValue
from app.validation.engine import summarize, validate_statement
from app.validation.identities import (
    INVARIANTS,
    IdentityResult,
    IdentityStatus,
    default_tolerance,
)


def make_statement(**values: float) -> FinancialStatement:
    """Build a FinancialStatement from {canonical_key: numeric_value}."""
    return FinancialStatement(items={key: FinancialValue(value=val) for key, val in values.items()})


def balanced_statement() -> FinancialStatement:
    """A fully self-consistent statement satisfying every invariant exactly."""
    return make_statement(
        # balance sheet
        total_current_assets=400.0,
        total_non_current_assets=600.0,
        total_assets=1000.0,
        total_current_liabilities=200.0,
        total_non_current_liabilities=300.0,
        total_liabilities=500.0,
        total_equity=500.0,
        # income statement
        revenue=1000.0,
        cost_of_goods_sold=600.0,
        gross_profit=400.0,
        operating_expenses=150.0,
        operating_income=250.0,
        pretax_income=200.0,
        income_tax_expense=50.0,
        net_income=150.0,
    )


def result_by_key(results: list[IdentityResult], key: str) -> IdentityResult:
    return next(r for r in results if r.key == key)


def test_balanced_statement_all_ok() -> None:
    results = validate_statement(balanced_statement())

    # Every defined invariant has inputs present, so none should be unavailable.
    assert len(results) == len(INVARIANTS)
    assert all(r.status is IdentityStatus.ok for r in results), [
        (r.key, r.status, r.detail) for r in results
    ]

    summary = summarize(results)
    assert summary["all_ok"] is True
    assert summary["has_mismatch"] is False
    assert summary["checked"] == len(INVARIANTS)
    assert summary["counts"][IdentityStatus.unavailable.value] == 0


def test_unbalanced_statement_reports_mismatch_with_difference() -> None:
    statement = balanced_statement()
    # Break the balance sheet: assets overstated by 120 vs liabilities + equity.
    statement.items["total_assets"] = FinancialValue(value=1120.0)

    results = validate_statement(statement)
    bse = result_by_key(results, "balance_sheet_equation")

    assert bse.status is IdentityStatus.mismatch
    assert bse.lhs == 1120.0
    assert bse.rhs == 1000.0  # 500 liabilities + 500 equity
    assert bse.difference == 120.0  # signed lhs - rhs
    assert bse.tolerance is not None and abs(bse.difference) > bse.tolerance
    assert bse.detail is not None

    # The asset-subtotal identity also breaks (subtotals 1000 vs total 1120).
    subtotal = result_by_key(results, "current_assets_subtotal")
    assert subtotal.status is IdentityStatus.mismatch
    assert subtotal.difference == -120.0  # 1000 - 1120

    summary = summarize(results)
    assert summary["has_mismatch"] is True
    assert summary["all_ok"] is False


def test_missing_inputs_reports_unavailable_with_missing_keys() -> None:
    # Only part of the balance-sheet equation is present.
    statement = make_statement(total_assets=1000.0, total_equity=500.0)

    results = validate_statement(statement)
    bse = result_by_key(results, "balance_sheet_equation")

    assert bse.status is IdentityStatus.unavailable
    assert bse.missing_inputs == ["total_liabilities"]
    # Never guesses a number when an input is missing.
    assert bse.lhs is None
    assert bse.rhs is None
    assert bse.difference is None
    assert bse.detail is not None and "total_liabilities" in bse.detail


def test_missing_inputs_lists_all_missing_in_input_order() -> None:
    statement = make_statement(revenue=1000.0)  # gross-profit identity missing two keys
    results = validate_statement(statement)
    gp = result_by_key(results, "gross_profit_identity")

    assert gp.status is IdentityStatus.unavailable
    assert gp.missing_inputs == ["cost_of_goods_sold", "gross_profit"]


def test_tolerance_absorbs_tiny_rounding() -> None:
    statement = balanced_statement()
    # Off by 0.4 — well inside the default tolerance (max(1.0, 1% of rhs)).
    statement.items["total_assets"] = FinancialValue(value=1000.4)

    results = validate_statement(statement)
    bse = result_by_key(results, "balance_sheet_equation")

    assert bse.status is IdentityStatus.ok
    assert bse.difference is not None and abs(bse.difference) <= (bse.tolerance or 0.0)


def test_default_tolerance_is_relative_above_minimum() -> None:
    # Below the 100-unit crossover the floor (1.0) dominates.
    assert default_tolerance(50.0) == 1.0
    # Above it, 1% of the rhs dominates.
    assert default_tolerance(10_000.0) == 100.0


def test_result_to_dict_is_json_friendly() -> None:
    results = validate_statement(balanced_statement())
    payload = result_by_key(results, "net_income_chain").to_dict()

    assert payload["key"] == "net_income_chain"
    assert payload["status"] == "ok"
    assert set(payload) == {
        "key",
        "name",
        "status",
        "lhs",
        "rhs",
        "difference",
        "tolerance",
        "missing_inputs",
        "detail",
    }
