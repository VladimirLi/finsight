"""Declarative catalogue of accounting IDENTITIES and result types.

An accounting identity is an equation that a correctly-extracted statement MUST
satisfy by construction — for example, total assets must equal total liabilities plus
total equity. Unlike a ratio (which derives a new number), an identity *checks* numbers
the document already reports against each other, catching extraction errors, sign
mistakes, and de-scaling bugs.

Each :class:`IdentityDefinition` declares:

* ``key`` / ``name`` — machine + human identifiers.
* ``inputs`` — the EXACT canonical line-item keys it requires. The engine screens for
  missing inputs BEFORE evaluating, so the ``lhs`` / ``rhs`` closures can assume every
  input is present and finite, keeping each formula a trivially auditable one-liner.
* ``lhs`` / ``rhs`` — pure functions over a dict of guaranteed-present floats. The check
  passes when ``lhs`` equals ``rhs`` within a relative tolerance.
* ``tolerance`` — an optional fixed absolute tolerance. When ``None`` the engine uses a
  sensible relative default (``max(1.0, 0.01 * abs(rhs))``) to absorb rounding / scaling
  noise without masking genuine errors.

Checks NEVER guess: a missing input yields ``unavailable`` with the missing keys listed,
never a fabricated number.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

# Default relative tolerance applied when an identity does not set an explicit one.
# We never demand exact equality: published statements round to the nearest reporting
# unit, and de-scaling ("in thousands") introduces sub-unit noise. One whole reporting
# unit, or 1% of the right-hand side, whichever is larger, absorbs that without hiding
# real extraction errors (which are typically off by orders of magnitude or a sign).
DEFAULT_RELATIVE_TOLERANCE = 0.01
DEFAULT_MINIMUM_TOLERANCE = 1.0


def default_tolerance(rhs: float) -> float:
    """Relative tolerance used when an identity declares no explicit tolerance."""
    return max(DEFAULT_MINIMUM_TOLERANCE, DEFAULT_RELATIVE_TOLERANCE * abs(rhs))


class IdentityStatus(StrEnum):
    """Outcome of checking an accounting identity."""

    ok = "ok"  # equation holds within tolerance
    mismatch = "mismatch"  # inputs present but equation violated
    unavailable = "unavailable"  # a required input was missing


@dataclass
class IdentityResult:
    """The evaluated result of one accounting identity check."""

    key: str
    name: str
    status: IdentityStatus
    lhs: float | None = None
    rhs: float | None = None
    difference: float | None = None  # lhs - rhs (signed), None when unavailable
    tolerance: float | None = None  # absolute tolerance actually applied
    missing_inputs: list[str] = field(default_factory=list)
    detail: str | None = None  # human-readable explanation, esp. when not ok

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serialisable representation of the result."""
        return {
            "key": self.key,
            "name": self.name,
            "status": self.status.value,
            "lhs": self.lhs,
            "rhs": self.rhs,
            "difference": self.difference,
            "tolerance": self.tolerance,
            "missing_inputs": self.missing_inputs,
            "detail": self.detail,
        }


@dataclass(frozen=True)
class IdentityDefinition:
    """Declarative definition of an accounting identity to validate."""

    key: str
    name: str
    inputs: list[str]  # required canonical keys
    lhs: Callable[[dict[str, float]], float]
    rhs: Callable[[dict[str, float]], float]
    description: str = ""
    # Fixed absolute tolerance. When None the engine uses ``default_tolerance(rhs)``.
    tolerance: float | None = None


# ---------------------------------------------------------------------------
# The catalogue of invariants. Each closure assumes the engine has already verified
# every key in ``inputs`` is present and finite.
# ---------------------------------------------------------------------------

INVARIANTS: list[IdentityDefinition] = [
    IdentityDefinition(
        key="balance_sheet_equation",
        name="Balance sheet equation",
        description="Total assets must equal total liabilities plus total equity.",
        inputs=["total_assets", "total_liabilities", "total_equity"],
        lhs=lambda f: f["total_assets"],
        rhs=lambda f: f["total_liabilities"] + f["total_equity"],
    ),
    IdentityDefinition(
        key="current_assets_subtotal",
        name="Asset subtotals reconcile",
        description="Current plus non-current assets must equal total assets.",
        inputs=["total_current_assets", "total_non_current_assets", "total_assets"],
        lhs=lambda f: f["total_current_assets"] + f["total_non_current_assets"],
        rhs=lambda f: f["total_assets"],
    ),
    IdentityDefinition(
        key="current_liabilities_subtotal",
        name="Liability subtotals reconcile",
        description="Current plus non-current liabilities must equal total liabilities.",
        inputs=[
            "total_current_liabilities",
            "total_non_current_liabilities",
            "total_liabilities",
        ],
        lhs=lambda f: f["total_current_liabilities"] + f["total_non_current_liabilities"],
        rhs=lambda f: f["total_liabilities"],
    ),
    IdentityDefinition(
        key="gross_profit_identity",
        name="Gross profit identity",
        description="Revenue minus cost of goods sold must equal gross profit.",
        inputs=["revenue", "cost_of_goods_sold", "gross_profit"],
        lhs=lambda f: f["revenue"] - f["cost_of_goods_sold"],
        rhs=lambda f: f["gross_profit"],
    ),
    IdentityDefinition(
        key="operating_income_identity",
        name="Operating income identity",
        description="Gross profit minus operating expenses must equal operating income.",
        inputs=["gross_profit", "operating_expenses", "operating_income"],
        lhs=lambda f: f["gross_profit"] - f["operating_expenses"],
        rhs=lambda f: f["operating_income"],
    ),
    IdentityDefinition(
        key="net_income_chain",
        name="Net income chain",
        description="Pretax income minus income tax expense must equal net income.",
        inputs=["pretax_income", "income_tax_expense", "net_income"],
        lhs=lambda f: f["pretax_income"] - f["income_tax_expense"],
        rhs=lambda f: f["net_income"],
    ),
]
