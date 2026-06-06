"""Deterministic accounting-identity validation layer.

This package checks that an extracted :class:`~app.schemas.financials.FinancialStatement`
internally obeys the accounting equations it MUST satisfy (e.g. assets = liabilities +
equity). Like the ratio engine, every check is a PURE PYTHON FUNCTION — never an LLM —
so identical inputs always yield identical, explainable verdicts. When a required input
is missing the check is reported as ``unavailable`` with the exact missing keys rather
than guessing; when inputs are present but the equation does not hold within tolerance
it is reported as ``mismatch`` with the precise difference. This directly serves the
product requirement that extracted data is correct, and that we say so when it is off.
"""

from __future__ import annotations

from app.validation.engine import summarize, validate_statement
from app.validation.identities import (
    INVARIANTS,
    IdentityDefinition,
    IdentityResult,
    IdentityStatus,
)

__all__ = [
    "INVARIANTS",
    "IdentityDefinition",
    "IdentityResult",
    "IdentityStatus",
    "summarize",
    "validate_statement",
]
