"""Deterministic ratio engine — framework and result types.

The whole point of this module: ratios are computed by PURE PYTHON FUNCTIONS, never
by an LLM. Each ratio declares exactly which canonical line items it needs. If any
required input is missing for a given period, the ratio is reported as UNAVAILABLE
together with the precise list of what was missing — so the UI can tell the user
"Current Ratio: N/A (missing: total_current_liabilities)" instead of a wrong number.

A ratio definition is a small declarative object:
    RatioDefinition(
        key="current_ratio",
        name="Current Ratio",
        category=RatioCategory.liquidity,
        inputs=["total_current_assets", "total_current_liabilities"],
        compute=lambda f: f["total_current_assets"] / f["total_current_liabilities"],
        ...
    )

``compute`` receives a plain dict of the required inputs, guaranteed non-None and
with zero-denominator already screened by the engine, so individual formulas stay
trivial and obviously correct.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from app.schemas.financials import FinancialStatement


class RatioCategory(StrEnum):
    """Functional grouping a ratio belongs to."""

    liquidity = "liquidity"
    leverage = "leverage"  # solvency / capital structure
    profitability = "profitability"
    efficiency = "efficiency"  # activity / turnover
    cash_flow = "cash_flow"
    valuation = "valuation"  # needs market data
    per_share = "per_share"


class RatioStatus(StrEnum):
    """Outcome of attempting to compute a ratio."""

    ok = "ok"
    unavailable = "unavailable"  # a required input was missing
    undefined = "undefined"  # math undefined, e.g. division by zero


@dataclass(frozen=True)
class RatioDefinition:
    """Declarative definition of a single financial ratio."""

    key: str
    name: str
    category: RatioCategory
    inputs: list[str]  # required canonical keys
    compute: Callable[[dict[str, float]], float]
    description: str = ""
    unit: str = "ratio"  # "ratio" | "percent" | "days" | "currency" | "x"
    higher_is_better: bool | None = None
    # Inputs that may come from a different source than the statement (e.g. market
    # price, market cap). Surfaced to the UI as "needs market data".
    market_inputs: list[str] = field(default_factory=list)


@dataclass
class RatioResult:
    """The computed (or unavailable) result for one ratio."""

    key: str
    name: str
    category: RatioCategory
    status: RatioStatus
    value: float | None = None
    unit: str = "ratio"
    missing_inputs: list[str] = field(default_factory=list)
    detail: str | None = None  # human-readable explanation, esp. when not ok

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serialisable representation of the result."""
        return {
            "key": self.key,
            "name": self.name,
            "category": self.category.value,
            "status": self.status.value,
            "value": self.value,
            "unit": self.unit,
            "missing_inputs": self.missing_inputs,
            "detail": self.detail,
        }


def evaluate_ratio(
    definition: RatioDefinition,
    statement: FinancialStatement,
    market_data: dict[str, float] | None = None,
) -> RatioResult:
    """Evaluate one ratio against one period, never raising on missing/bad data."""
    market_data = market_data or {}
    available: dict[str, float] = {}
    missing: list[str] = []

    for key in definition.inputs:
        val = statement.get(key)
        if val is None:
            missing.append(key)
        else:
            available[key] = val

    for key in definition.market_inputs:
        if key in market_data:
            available[key] = market_data[key]
        else:
            missing.append(key)

    if missing:
        return RatioResult(
            key=definition.key,
            name=definition.name,
            category=definition.category,
            status=RatioStatus.unavailable,
            unit=definition.unit,
            missing_inputs=missing,
            detail=f"Cannot compute: missing {', '.join(missing)}.",
        )

    try:
        value = definition.compute(available)
    except ZeroDivisionError:
        return RatioResult(
            key=definition.key,
            name=definition.name,
            category=definition.category,
            status=RatioStatus.undefined,
            unit=definition.unit,
            detail="Undefined (division by zero).",
        )

    if value != value or value in (float("inf"), float("-inf")):  # NaN / inf guard
        return RatioResult(
            key=definition.key,
            name=definition.name,
            category=definition.category,
            status=RatioStatus.undefined,
            unit=definition.unit,
            detail="Undefined (non-finite result).",
        )

    return RatioResult(
        key=definition.key,
        name=definition.name,
        category=definition.category,
        status=RatioStatus.ok,
        value=value,
        unit=definition.unit,
    )
