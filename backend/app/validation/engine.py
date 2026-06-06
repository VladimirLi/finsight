"""Deterministic accounting-identity validation engine.

Single entry point the API layer calls to check whether a canonical
:class:`~app.schemas.financials.FinancialStatement` internally obeys the accounting
equations it must satisfy. It does NO arithmetic of its own beyond comparing each
identity's two sides within tolerance: it maps :func:`evaluate_identity` over every
definition in :data:`~app.validation.identities.INVARIANTS`. All the equation logic
lives in the pure ``lhs`` / ``rhs`` closures declared in ``identities.py``; all the
missing-input / non-finite guarding lives here.

Crucially, identities are NEVER checked by an LLM — only by these vetted Python
formulas — so identical inputs always yield identical, explainable verdicts.
"""

from __future__ import annotations

from math import isfinite
from typing import Any

from app.schemas.financials import FinancialStatement
from app.validation.identities import (
    INVARIANTS,
    IdentityDefinition,
    IdentityResult,
    IdentityStatus,
    default_tolerance,
)


def evaluate_identity(
    definition: IdentityDefinition,
    statement: FinancialStatement,
) -> IdentityResult:
    """Evaluate one identity against one statement, never raising on missing/bad data."""
    available: dict[str, float] = {}
    missing: list[str] = []

    for key in definition.inputs:
        val = statement.get(key)
        if val is None:
            missing.append(key)
        else:
            available[key] = val

    if missing:
        return IdentityResult(
            key=definition.key,
            name=definition.name,
            status=IdentityStatus.unavailable,
            missing_inputs=missing,
            detail=f"Cannot check: missing {', '.join(missing)}.",
        )

    lhs = definition.lhs(available)
    rhs = definition.rhs(available)

    if not (isfinite(lhs) and isfinite(rhs)):
        return IdentityResult(
            key=definition.key,
            name=definition.name,
            status=IdentityStatus.unavailable,
            detail="Cannot check: non-finite operand.",
        )

    difference = lhs - rhs
    tolerance = definition.tolerance if definition.tolerance is not None else default_tolerance(rhs)

    if abs(difference) <= tolerance:
        return IdentityResult(
            key=definition.key,
            name=definition.name,
            status=IdentityStatus.ok,
            lhs=lhs,
            rhs=rhs,
            difference=difference,
            tolerance=tolerance,
        )

    return IdentityResult(
        key=definition.key,
        name=definition.name,
        status=IdentityStatus.mismatch,
        lhs=lhs,
        rhs=rhs,
        difference=difference,
        tolerance=tolerance,
        detail=(
            f"Identity violated: lhs={lhs:g} vs rhs={rhs:g} "
            f"(difference {difference:g} exceeds tolerance {tolerance:g})."
        ),
    )


def validate_statement(statement: FinancialStatement) -> list[IdentityResult]:
    """Check every defined accounting identity for a single statement.

    Returns one :class:`IdentityResult` per definition, in catalogue order. Every
    result is well-formed; this function never raises on missing or malformed data.
    Identities whose inputs are absent are reported as ``unavailable`` (not skipped),
    so callers can always show the full checklist.
    """
    return [evaluate_identity(definition, statement) for definition in INVARIANTS]


def summarize(results: list[IdentityResult]) -> dict[str, Any]:
    """Roll up identity results into a compact summary for the API / UI.

    Reports counts per status and an overall boolean: ``all_ok`` is True only when at
    least one identity could be checked AND none mismatched. ``has_mismatch`` flags any
    violated identity so the UI can warn that extracted figures do not reconcile.
    """
    counts: dict[str, int] = {status.value: 0 for status in IdentityStatus}
    for result in results:
        counts[result.status.value] += 1

    checked = counts[IdentityStatus.ok.value] + counts[IdentityStatus.mismatch.value]
    return {
        "total": len(results),
        "counts": counts,
        "checked": checked,
        "has_mismatch": counts[IdentityStatus.mismatch.value] > 0,
        "all_ok": checked > 0 and counts[IdentityStatus.mismatch.value] == 0,
    }
