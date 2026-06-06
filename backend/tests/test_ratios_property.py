"""Property-based tests for the deterministic ratio engine (Hypothesis).

Where ``test_ratios.py`` checks hand-computed example values, this module asserts
*invariants* that must hold for EVERY ratio against ANY randomly-generated
statement. Hypothesis fuzzes both the SET of canonical fields present and their
numeric values, so the engine is exercised across sparse, dense, zero-laden and
extreme-magnitude inputs.

Invariants asserted for every ``RatioResult`` produced by ``compute_all_ratios``:

* The engine NEVER raises — ``evaluate_ratio`` catches division-by-zero and
  screens NaN/inf, so a result object is always returned.
* ``status`` is always one of ``ok`` | ``unavailable`` | ``undefined``.
* If any required statement input is absent, the status is ``unavailable`` and
  ``missing_inputs`` is EXACTLY the set of absent required inputs (statement
  inputs that were None/missing, plus any required market input not supplied).
* When status is ``ok`` the value is a finite float, ``missing_inputs`` is empty,
  and the result ``unit`` matches the definition's declared unit.
* When status is ``unavailable`` the value is None; when ``undefined`` the value
  is None.
* Percent-unit ratios are scaled consistently with their definition: recomputing
  the formula by hand on the same inputs reproduces the engine's value, so the
  ``* 100`` scaling declared in ``definitions.py`` is faithfully applied.
"""

from __future__ import annotations

import math

from app.ratios.base import (
    RatioDefinition,
    RatioStatus,
    evaluate_ratio,
)
from app.ratios.definitions import RATIO_DEFINITIONS
from app.ratios.engine import compute_all_ratios
from app.schemas.financials import (
    ALL_CANONICAL_FIELDS,
    FinancialStatement,
    FinancialValue,
)
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

# Market inputs referenced by any valuation ratio (collected from the catalogue
# so the test stays in sync with definitions.py without hard-coding the keys).
_ALL_MARKET_INPUTS: list[str] = sorted({key for d in RATIO_DEFINITIONS for key in d.market_inputs})

# Bounded, finite floats. We deliberately INCLUDE 0.0 and negatives so the engine's
# zero-denominator and non-finite guards get exercised, but exclude NaN/inf at the
# input boundary (the model stores real reported numbers, never NaN/inf).
_finite_floats = st.floats(
    min_value=-1e9,
    max_value=1e9,
    allow_nan=False,
    allow_infinity=False,
)

_VALID_STATUSES = {RatioStatus.ok, RatioStatus.unavailable, RatioStatus.undefined}


@st.composite
def _statements(draw: st.DrawFn) -> FinancialStatement:
    """Generate a FinancialStatement with a random subset of canonical fields.

    Each chosen field gets a random finite value. Fields not chosen are simply
    absent (the engine treats them as None → unavailable for any ratio needing
    them), exercising the missing-input path on every run.
    """
    chosen = draw(
        st.lists(
            st.sampled_from(ALL_CANONICAL_FIELDS),
            unique=True,
            max_size=len(ALL_CANONICAL_FIELDS),
        )
    )
    items: dict[str, FinancialValue] = {
        key: FinancialValue(value=draw(_finite_floats)) for key in chosen
    }
    return FinancialStatement(items=items)


@st.composite
def _market_data(draw: st.DrawFn) -> dict[str, float]:
    """Generate an optional partial market-data dict (may omit required keys)."""
    if not _ALL_MARKET_INPUTS:
        return {}
    chosen = draw(st.lists(st.sampled_from(_ALL_MARKET_INPUTS), unique=True))
    return {key: draw(_finite_floats) for key in chosen}


def _expected_missing(
    definition: RatioDefinition,
    statement: FinancialStatement,
    market_data: dict[str, float],
) -> list[str]:
    """Recompute, independently of the engine, the exact missing-inputs list.

    Mirrors ``evaluate_ratio``'s ordering: statement inputs first (in declared
    order), then market inputs (in declared order).
    """
    missing: list[str] = []
    for key in definition.inputs:
        if statement.get(key) is None:
            missing.append(key)
    for key in definition.market_inputs:
        if key not in market_data:
            missing.append(key)
    return missing


@settings(
    max_examples=250,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow],
)
@given(statement=_statements(), market_data=_market_data())
def test_engine_invariants_hold_for_every_ratio(
    statement: FinancialStatement,
    market_data: dict[str, float],
) -> None:
    """Every ratio result is well-formed under any random statement + market data."""
    # The engine must never raise, regardless of how sparse/extreme the inputs are.
    results = compute_all_ratios(statement, market_data=market_data)

    # One result per definition, in catalogue order.
    assert len(results) == len(RATIO_DEFINITIONS)

    for definition, result in zip(RATIO_DEFINITIONS, results, strict=True):
        # --- identity / status domain --------------------------------------
        assert result.key == definition.key
        assert result.unit == definition.unit
        assert result.status in _VALID_STATUSES

        expected_missing = _expected_missing(definition, statement, market_data)

        if expected_missing:
            # Any absent required input => unavailable with the EXACT missing set.
            assert result.status is RatioStatus.unavailable, (
                f"{definition.key}: expected unavailable when inputs missing"
            )
            assert result.missing_inputs == expected_missing
            assert result.value is None
            continue

        # All inputs present: result is either ok (finite) or undefined (math).
        assert result.missing_inputs == []
        if result.status is RatioStatus.ok:
            assert result.value is not None
            assert math.isfinite(result.value)
        else:
            assert result.status is RatioStatus.undefined
            assert result.value is None


@settings(
    max_examples=250,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow],
)
@given(statement=_statements(), market_data=_market_data())
def test_ok_values_match_direct_compute(
    statement: FinancialStatement,
    market_data: dict[str, float],
) -> None:
    """For every ``ok`` result, the engine value equals the definition's own formula.

    This pins down unit scaling end-to-end: percent ratios that multiply by 100 in
    ``definitions.py`` must surface a 0..100-scaled value, and the engine must not
    re-scale or drop the factor. We reconstruct the input dict exactly as the
    engine does and call the definition's ``compute`` directly.
    """
    for definition in RATIO_DEFINITIONS:
        result = evaluate_ratio(definition, statement, market_data=market_data)
        if result.status is not RatioStatus.ok:
            continue

        available: dict[str, float] = {}
        for key in definition.inputs:
            val = statement.get(key)
            assert val is not None  # guaranteed by ok status
            available[key] = val
        for key in definition.market_inputs:
            available[key] = market_data[key]

        expected = definition.compute(available)
        assert result.value is not None
        assert math.isfinite(expected)
        # Exact equality: the engine performs no transformation of its own — it
        # returns precisely what ``compute`` produced.
        assert result.value == expected


@settings(
    max_examples=200,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow],
)
@given(statement=_statements(), market_data=_market_data())
def test_percent_ratios_are_scaled_to_100(
    statement: FinancialStatement,
    market_data: dict[str, float],
) -> None:
    """Percent-unit ratios reflect the documented ``* 100`` scaling.

    For a percent ratio, the engine value must equal 100x the same formula computed
    without the scaling factor (i.e. the underlying fraction). We verify this by
    recomputing the unscaled fraction from the raw inputs for each percent ratio.
    """
    # Map each percent ratio key to a function returning its UNSCALED fraction.
    # These mirror definitions.py with the ``* 100`` removed.
    unscaled: dict[str, object] = {
        "gross_margin": lambda f: f["gross_profit"] / f["revenue"],
        "operating_margin": lambda f: f["operating_income"] / f["revenue"],
        "net_margin": lambda f: f["net_income"] / f["revenue"],
        "return_on_assets": lambda f: f["net_income"] / f["total_assets"],
        "return_on_equity": lambda f: f["net_income"] / f["total_equity"],
        "return_on_invested_capital": (
            lambda f: f["operating_income"] / (f["long_term_debt"] + f["total_equity"])
        ),
        "ebitda_margin": lambda f: f["ebitda"] / f["revenue"],
        "fcf_margin": (
            lambda f: (f["operating_cash_flow"] + f["capital_expenditures"]) / f["revenue"]
        ),
        "capex_to_revenue": lambda f: abs(f["capital_expenditures"]) / f["revenue"],
        "dividend_payout_ratio": lambda f: abs(f["dividends_paid"]) / f["net_income"],
    }

    for definition in RATIO_DEFINITIONS:
        if definition.unit != "percent":
            continue
        assert definition.key in unscaled, (
            f"percent ratio {definition.key} not covered by scaling test"
        )
        result = evaluate_ratio(definition, statement, market_data=market_data)
        if result.status is not RatioStatus.ok:
            continue

        available: dict[str, float] = {
            key: v for key in definition.inputs if (v := statement.get(key)) is not None
        }
        fraction_fn = unscaled[definition.key]
        fraction = fraction_fn(available)  # type: ignore[operator]
        assert result.value is not None
        # value == fraction * 100, allowing for floating-point rounding.
        assert math.isclose(result.value, fraction * 100.0, rel_tol=1e-9, abs_tol=1e-9)
