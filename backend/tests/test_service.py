"""End-to-end (in-memory DB) tests for app.extraction.service.

Exercises ``process_document`` through the full parse -> extract -> persist
pipeline with the OCR engine and LLM provider replaced by deterministic fakes,
plus targeted unit tests for ``merge_statements`` (human-edit precedence).

No network, no real LLM, and no real ``finsight.db``: ``process_document``
opens its own ``SessionLocal`` session, so we monkeypatch
``app.extraction.service.SessionLocal`` onto the in-memory factory.
"""

from __future__ import annotations

from typing import Any

import pytest
from app.db.models import Company, Document, FinancialPeriod
from app.extraction import service
from app.schemas.financials import FinancialStatement, FinancialValue, PeriodType
from sqlalchemy.orm import Session, sessionmaker

from tests.conftest import FakeLLMProvider, FakeOCREngine, build_parsed_document


def _income_statement_doc() -> Any:
    """A parsed doc whose text triggers income-statement detection."""
    return build_parsed_document(
        filename="acme_10k.pdf",
        pages=[
            (
                "ACME CORP\nConsolidated Income Statement\n"
                "Revenue ... Net income ... Earnings per share",
                [["Revenue", "1,000,000"], ["Net income", "200,000"]],
            ),
        ],
    )


def _payload(
    *,
    revenue: str = "1,000,000",
    net_income: str = "200,000",
    period_type: str | None = None,
) -> dict[str, Any]:
    """Build a canned LLM payload.

    ``period_type`` defaults to ``None`` so tests that don't care about it stay
    terse. A non-None StrEnum period_type round-trips cleanly through the
    strict model_dump(json)->model_validate cycle the DB layer uses, because
    the field declares ``strict=False`` (see app/schemas/financials.py);
    test_persisted_period_type_reads_back exercises that case explicitly.
    """
    return {
        "company_name": "Acme Corp",
        "ticker": "ACME",
        "currency": "USD",
        "period_type": period_type,
        "fiscal_year": 2023,
        "fiscal_period_end": "2023-12-31",
        "units_scale_note": None,
        "items": {
            "revenue": {"value": revenue, "source_page": 1, "confidence": 0.9},
            "net_income": {"value": net_income, "source_page": 1, "confidence": 0.9},
        },
    }


@pytest.fixture
def wired(
    monkeypatch: pytest.MonkeyPatch,
    session_factory: sessionmaker[Session],
) -> sessionmaker[Session]:
    """Wire service.SessionLocal and the OCR/LLM factories to fakes.

    Returns the in-memory session factory so the test can assert on the DB.
    """
    monkeypatch.setattr(service, "SessionLocal", session_factory)
    return session_factory


def _patch_engines(
    monkeypatch: pytest.MonkeyPatch,
    *,
    doc: Any,
    payload: dict[str, Any],
) -> None:
    """Patch the lazily-imported OCR engine + LLM provider factories."""
    import app.llm.factory as llm_factory
    import app.ocr.factory as ocr_factory

    monkeypatch.setattr(ocr_factory, "get_ocr_engine", lambda: FakeOCREngine(doc))
    monkeypatch.setattr(llm_factory, "get_provider", lambda *a, **k: FakeLLMProvider(payload))


def _make_document(factory: sessionmaker[Session]) -> int:
    """Insert an 'uploaded' Document and return its id."""
    db = factory()
    try:
        doc_row = Document(
            filename="acme_10k.pdf",
            stored_path="/tmp/does-not-matter.pdf",
            status="uploaded",
        )
        db.add(doc_row)
        db.commit()
        db.refresh(doc_row)
        return doc_row.id
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Full pipeline
# ---------------------------------------------------------------------------


def test_process_document_end_to_end(
    wired: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A fake document flows through parse -> extract -> persist into the DB."""
    _patch_engines(monkeypatch, doc=_income_statement_doc(), payload=_payload())
    doc_id = _make_document(wired)

    service.process_document(doc_id)

    db = wired()
    try:
        # Company upserted from extracted metadata.
        company = db.query(Company).one()
        assert company.name == "Acme Corp"
        assert company.ticker == "ACME"
        assert company.currency == "USD"

        # Period created and linked.
        period = db.query(FinancialPeriod).one()
        assert period.company_id == company.id
        assert period.fiscal_year == 2023
        assert period.fiscal_period_end == "2023-12-31"

        # Statement persisted with coerced numeric values.
        stmt = service.get_statement(period)
        assert stmt.get("revenue") == pytest.approx(1_000_000.0)
        assert stmt.get("net_income") == pytest.approx(200_000.0)

        # Document transitioned to needs_review and linked to the period.
        document = db.get(Document, doc_id)
        assert document is not None
        assert document.status == "needs_review"
        assert document.error is None
        assert document.period_id == period.id
        assert document.num_pages == 1
        assert document.detected_statement_types is not None
        assert "income_statement" in document.detected_statement_types
    finally:
        db.close()


def test_process_document_with_explicit_company(
    wired: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Passing company_id attaches the period to that company (no upsert)."""
    _patch_engines(monkeypatch, doc=_income_statement_doc(), payload=_payload())

    db = wired()
    try:
        existing = Company(name="Pre-existing Inc", ticker="PRE", currency="USD")
        db.add(existing)
        db.commit()
        db.refresh(existing)
        company_id = existing.id
    finally:
        db.close()

    doc_id = _make_document(wired)
    service.process_document(doc_id, company_id=company_id)

    db = wired()
    try:
        # No second company was created.
        assert db.query(Company).count() == 1
        period = db.query(FinancialPeriod).one()
        assert period.company_id == company_id
    finally:
        db.close()


def test_process_document_missing_company_fails(
    wired: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A bogus company_id transitions the document to 'failed' without raising."""
    _patch_engines(monkeypatch, doc=_income_statement_doc(), payload=_payload())
    doc_id = _make_document(wired)

    service.process_document(doc_id, company_id=99999)

    db = wired()
    try:
        document = db.get(Document, doc_id)
        assert document is not None
        assert document.status == "failed"
        assert document.error is not None
        assert "99999" in document.error
        # No period persisted on failure.
        assert db.query(FinancialPeriod).count() == 0
    finally:
        db.close()


def test_persisted_period_type_reads_back(
    wired: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression: persisting a period_type then reading it back round-trips cleanly.

    Previously broke because set_statement stored the JSON string 'FY' and
    get_statement re-validated under strict=True. The period_type field now declares
    strict=False, so the read-back coerces 'FY' back into PeriodType.
    """
    _patch_engines(
        monkeypatch,
        doc=_income_statement_doc(),
        payload=_payload(period_type="FY"),
    )
    doc_id = _make_document(wired)
    service.process_document(doc_id)

    db = wired()
    try:
        period = db.query(FinancialPeriod).one()
        statement = service.get_statement(period)  # must not raise
        assert statement.period_type == PeriodType.fiscal_year
    finally:
        db.close()


def test_re_extraction_preserves_human_edits(
    wired: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Re-running extraction must NOT overwrite a value edited_by_user=True."""
    # First extraction.
    _patch_engines(monkeypatch, doc=_income_statement_doc(), payload=_payload())
    doc_id = _make_document(wired)
    service.process_document(doc_id)

    # Human corrects net_income on the persisted period.
    db = wired()
    try:
        period = db.query(FinancialPeriod).one()
        service.apply_item_updates(db, period, {"net_income": 999_999.0})
        period_id = period.id
    finally:
        db.close()

    # Re-extract the SAME period (same company/year/type) with different numbers.
    _patch_engines(
        monkeypatch,
        doc=_income_statement_doc(),
        payload=_payload(revenue="1,500,000", net_income="42"),
    )
    doc2_id = _make_document(wired)
    service.process_document(doc2_id)

    db = wired()
    try:
        # Still a single period (deduplicated on company/year/type).
        reread = db.get(FinancialPeriod, period_id)
        assert reread is not None
        stmt = service.get_statement(reread)

        # Human-edited net_income is preserved; non-edited revenue is updated.
        assert stmt.get("net_income") == pytest.approx(999_999.0)
        assert stmt.items["net_income"].edited_by_user is True
        assert stmt.get("revenue") == pytest.approx(1_500_000.0)
    finally:
        db.close()


# ---------------------------------------------------------------------------
# merge_statements unit behaviour
# ---------------------------------------------------------------------------


def test_merge_statements_respects_edited_by_user() -> None:
    """merge_statements keeps an edited_by_user value over an incoming one."""
    existing = FinancialStatement(
        company_name="Acme",
        items={
            "revenue": FinancialValue(value=100.0, edited_by_user=True),
            "net_income": FinancialValue(value=10.0, edited_by_user=False),
        },
    )
    incoming = FinancialStatement(
        company_name="Acme",
        currency="USD",
        items={
            "revenue": FinancialValue(value=999.0),
            "net_income": FinancialValue(value=20.0),
        },
    )

    merged = service.merge_statements(existing, incoming)

    # Human-edited value wins; provenance flag preserved.
    assert merged.get("revenue") == pytest.approx(100.0)
    assert merged.items["revenue"].edited_by_user is True
    # Non-edited value is overwritten by the fresh extraction.
    assert merged.get("net_income") == pytest.approx(20.0)
    # Incoming non-None metadata fills in.
    assert merged.currency == "USD"


def test_merge_statements_retains_existing_when_incoming_absent() -> None:
    """A non-edited existing value is retained when incoming has no entry."""
    existing = FinancialStatement(
        items={"revenue": FinancialValue(value=100.0, edited_by_user=False)},
    )
    incoming = FinancialStatement(items={})

    merged = service.merge_statements(existing, incoming)
    assert merged.get("revenue") == pytest.approx(100.0)


def test_merge_statements_does_not_mutate_inputs() -> None:
    """merge_statements returns a new statement, mutating neither argument."""
    existing = FinancialStatement(items={"revenue": FinancialValue(value=1.0)})
    incoming = FinancialStatement(items={"revenue": FinancialValue(value=2.0)})

    service.merge_statements(existing, incoming)

    assert existing.get("revenue") == pytest.approx(1.0)
    assert incoming.get("revenue") == pytest.approx(2.0)
