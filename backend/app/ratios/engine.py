"""Deterministic ratio computation engine.

This module is the single entry point the API layer calls to turn a canonical
:class:`~app.schemas.financials.FinancialStatement` into a list of
:class:`~app.ratios.base.RatioResult`. It does NO arithmetic itself: it simply maps
:func:`~app.ratios.base.evaluate_ratio` over every definition in
:data:`~app.ratios.definitions.RATIO_DEFINITIONS`. All the math lives in the pure
``compute`` closures declared in ``definitions.py``; all the missing-input /
zero-denominator / non-finite guarding lives in ``evaluate_ratio``.

Crucially, ratios are NEVER computed by an LLM — only by these vetted Python
formulas — so identical inputs always yield identical, explainable outputs.
"""

from __future__ import annotations

from app.ratios.base import RatioCategory, RatioResult, evaluate_ratio
from app.ratios.definitions import RATIO_DEFINITIONS
from app.schemas.financials import FinancialStatement


def compute_all_ratios(
    statement: FinancialStatement,
    market_data: dict[str, float] | None = None,
) -> list[RatioResult]:
    """Compute every defined ratio for a single company-period.

    Parameters
    ----------
    statement:
        The canonical financial statement for one period.
    market_data:
        Optional mapping of market-sourced inputs (e.g. ``{"market_price": 123.4}``)
        required by valuation ratios. Ratios needing market inputs not present here
        are reported as ``unavailable`` with those inputs listed in ``missing_inputs``.

    Returns:
    -------
    list[RatioResult]
        One result per definition, in catalogue order. Every result is well-formed;
        this function never raises on missing or malformed data.
    """
    return [
        evaluate_ratio(definition, statement, market_data=market_data)
        for definition in RATIO_DEFINITIONS
    ]


def grouped_by_category(
    results: list[RatioResult],
) -> dict[str, list[RatioResult]]:
    """Group ratio results by their category value, preserving input order.

    The returned dict is keyed by the category's string value (e.g. "liquidity")
    so it serialises cleanly to JSON for the UI. Categories with no results are
    omitted. Every category present in :class:`RatioCategory` is considered, in
    declaration order, so the output is stable and predictable.
    """
    grouped: dict[str, list[RatioResult]] = {}
    # Seed in enum-declaration order so categories appear in a stable, sensible order.
    order = {category.value: index for index, category in enumerate(RatioCategory)}
    for result in results:
        grouped.setdefault(result.category.value, []).append(result)
    # Re-key into a new dict ordered by the canonical category order.
    return {key: grouped[key] for key in sorted(grouped, key=lambda k: order.get(k, len(order)))}
