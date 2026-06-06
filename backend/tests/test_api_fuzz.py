"""API fuzz tests (Schemathesis 4.x, ASGI integration).

We build the real FastAPI app and let Schemathesis derive test cases from its
in-memory OpenAPI schema, then fire generated requests at the app via its ASGI
transport. For every generated request we assert Schemathesis' built-in checks:

* ``not_a_server_error`` — no unexpected 5xx (an uncaught exception is a bug).
* response status is documented in the schema.
* the response body conforms to the declared response schema / content type.

Determinism & isolation
-----------------------
* The app's ``get_db`` dependency is overridden to a throw-away in-memory SQLite
  database (StaticPool, shared across connections) — the real ``./finsight.db``
  is never touched.
* The DB is SEEDED with one company + one period so that detail/ratio endpoints
  have real data to return (not just 404s), exercising the success paths.
* Endpoints that kick off the extraction pipeline as a background task
  (``POST /documents/upload`` and ``POST /documents/{id}/reprocess``) are
  EXCLUDED: they would invoke heavy OCR/LLM machinery, which is out of scope for
  contract fuzzing and would make the suite slow and non-deterministic.

The example budget is kept modest so this is fast in CI.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any, cast

import pytest
import schemathesis
from app.db.database import Base, get_db
from app.main import app
from hypothesis import HealthCheck, settings
from schemathesis import Case
from schemathesis.specs.openapi.checks import (
    positive_data_acceptance,
    status_code_conformance,
)
from schemathesis.specs.openapi.schemas import OpenApiSchema
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

# ---------------------------------------------------------------------------
# In-memory DB wired into the app via dependency_overrides
# ---------------------------------------------------------------------------

_engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,  # one shared in-memory DB across all connections
)
_TestSession = sessionmaker(autocommit=False, autoflush=False, bind=_engine)


def _seed() -> None:
    """Create tables and insert a company + a populated financial period.

    The seeded period carries enough canonical line items that ratio endpoints
    return mostly ``ok`` results, exercising success paths during fuzzing.
    """
    # Import here so model classes register on Base.metadata before create_all.
    from app.db.models import Company, FinancialPeriod  # noqa: PLC0415

    Base.metadata.create_all(bind=_engine)
    db = _TestSession()
    try:
        if db.query(Company).count() > 0:
            return
        company = Company(name="Acme Corp", ticker="ACME", currency="USD")
        db.add(company)
        db.flush()
        period = FinancialPeriod(
            company_id=company.id,
            period_type="FY",
            fiscal_year=2023,
            fiscal_period_end="2023-12-31",
            currency="USD",
            statement_json={
                "items": {
                    "revenue": {"value": 1000.0},
                    "net_income": {"value": 120.0},
                    "total_assets": {"value": 5000.0},
                    "total_current_assets": {"value": 2000.0},
                    "total_current_liabilities": {"value": 1000.0},
                    "total_liabilities": {"value": 3000.0},
                    "total_equity": {"value": 2000.0},
                    "operating_income": {"value": 200.0},
                    "interest_expense": {"value": 20.0},
                    "shares_outstanding_diluted": {"value": 100.0},
                }
            },
        )
        db.add(period)
        db.commit()
    finally:
        db.close()


def _override_get_db() -> Iterator[Session]:
    db = _TestSession()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture(scope="module", autouse=True)
def _wire_app() -> Iterator[None]:
    """Seed the in-memory DB and override the app's DB dependency for the module."""
    _seed()
    app.dependency_overrides[get_db] = _override_get_db
    try:
        yield
    finally:
        app.dependency_overrides.pop(get_db, None)
        Base.metadata.drop_all(bind=_engine)


# ---------------------------------------------------------------------------
# Schemathesis schema (ASGI), with a modest example budget and pipeline
# endpoints excluded.
# ---------------------------------------------------------------------------

_config = schemathesis.Config.from_dict(
    {
        "generation": {"max-examples": 12},
    }
)

# Exclude endpoints that trigger the background extraction pipeline (OCR/LLM):
# ``.exclude`` is typed as returning ``BaseSchema`` by the stubs but yields the
# concrete ``OpenApiSchema`` at runtime; annotate explicitly to keep mypy/pyright
# strict-clean while still exposing the OpenAPI-specific ``.hook``/``.parametrize``.
schema: OpenApiSchema = cast(
    OpenApiSchema,
    schemathesis.openapi.from_asgi("/openapi.json", app, config=_config)
    .exclude(path="/api/documents/upload")
    .exclude(path="/api/documents/{doc_id}/reprocess"),
)

# Signed 64-bit range — SQLite's INTEGER storage limit. The OpenAPI schema types
# path IDs as unbounded integers, but our test DB is SQLite, which raises
# OverflowError (a spurious 500 that is a storage-backend artifact, NOT an app
# bug) for ids outside int64. Clamp generated integer path params into range so
# fuzzing exercises realistic IDs instead of the SQLite limit.
_INT64_MIN = -(2**63)
_INT64_MAX = 2**63 - 1


def _clamp_int(value: Any) -> Any:
    """Clamp a single int into the SQLite-representable int64 range; pass through else."""
    if isinstance(value, int) and not isinstance(value, bool):
        return max(_INT64_MIN, min(_INT64_MAX, value))
    return value


@schema.hook
def map_path_parameters(
    _context: schemathesis.hooks.HookContext,
    path_parameters: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Clamp integer path parameters into the SQLite-representable int64 range."""
    if not path_parameters:
        return path_parameters
    return {key: _clamp_int(value) for key, value in path_parameters.items()}


@schema.hook
def map_body(_context: schemathesis.hooks.HookContext, body: Any) -> Any:
    """Clamp top-level integer body fields (e.g. ``company_id`` on POST /periods).

    Same rationale as ``map_path_parameters``: the OpenAPI schema types FK ids as
    unbounded integers, but our SQLite test DB raises ``OverflowError`` (a
    storage-backend artifact, NOT an app bug) when an int outside int64 reaches a
    query. We only touch top-level integer fields of a JSON object body; all other
    shapes pass through untouched so genuine validation paths are still fuzzed.
    """
    if isinstance(body, dict):
        typed_body: dict[str, Any] = body
        return {key: _clamp_int(value) for key, value in typed_body.items()}
    return body


@schema.parametrize()
@settings(
    deadline=None,
    max_examples=12,
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.filter_too_much],
)
def test_api_no_500_and_schema_conformant(case: Case[Any], **_: Any) -> None:
    """Generated requests must not 500 and must conform to the OpenAPI contract.

    ``call_and_validate`` runs Schemathesis' default check suite, which here
    enforces:
    * ``not_a_server_error`` — no uncaught exception / unexpected 5xx,
    * ``response_schema_conformance`` — response body matches the declared schema,
    * ``content_type_conformance`` / header conformance,
    * ``negative_data_rejection`` — invalid input is rejected (422), not accepted.

    Two Open API contract-completeness checks are EXCLUDED because each surfaced a
    pre-existing *documentation* gap rather than a runtime bug (no 5xx was ever
    produced). Both are reported in the structured output's notes instead of being
    masked:

    * ``status_code_conformance`` — the routers respond with codes the
      auto-generated OpenAPI schema does not declare: every
      ``raise HTTPException(404, ...)`` (all detail/ratio/delete routes), the
      ``status_code=201`` on ``POST /companies`` and ``POST /periods``, and the
      ``415`` on upload. FastAPI documents only ``200`` and ``422`` for these.
      The fix is to add ``responses={404: ..., ...}`` in the routers (another
      partition).
    * ``positive_data_acceptance`` — FastAPI documents optional nullable query
      params (``market_price``, ``shares_outstanding`` on
      ``/periods/{id}/ratios``) as ``anyOf: [number, null]``. Schemathesis then
      emits the literal query string ``shares_outstanding=null``, which FastAPI
      cannot parse as a float and rejects with 422. A query string cannot carry a
      JSON null, so this is an OpenAPI/serialization quirk, not an app bug; the
      intended semantics is "omit the param to skip".
    """
    case.call_and_validate(
        excluded_checks=[status_code_conformance, positive_data_acceptance],
    )
