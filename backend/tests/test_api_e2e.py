"""HTTP end-to-end tests for the full document → review → ratios journey.

This is the integration tier of the test pyramid: every assertion goes through
the real FastAPI routes via ``TestClient`` (not by calling service functions
directly), so it exercises request validation, response serialization, the
background-task hand-off, and the OpenAPI contract together.

Determinism is preserved exactly like the rest of the suite — no network, no
real LLM, no real ``finsight.db``:

  * ``get_db`` is overridden to the in-memory SQLite factory (via the ``client``
    fixture in conftest);
  * ``service.SessionLocal`` is monkeypatched onto that SAME factory so the
    upload background task writes to the in-memory DB the requests read from;
  * the OCR engine and LLM provider factories are replaced with deterministic
    fakes;
  * ``upload_dir`` is redirected to a tmp path so no files land in ./uploads.

Starlette's ``TestClient`` runs background tasks synchronously before the
request returns, so by the time ``POST /documents/upload`` responds the
pipeline has already advanced the document to ``needs_review``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from app.extraction import service
from sqlalchemy.orm import Session, sessionmaker

from tests.conftest import FakeLLMProvider, FakeOCREngine, build_parsed_document

# A minimal byte blob standing in for a PDF. FakeOCREngine ignores file contents,
# so the bytes only need to satisfy the upload route's size/None checks.
_FAKE_PDF = b"%PDF-1.4 fake bytes for testing\n"


def _income_doc() -> Any:
    """A parsed doc whose page text triggers income-statement detection."""
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


def _payload() -> dict[str, Any]:
    """Canned extraction result with enough fields to compute real ratios."""
    return {
        "company_name": "Acme Corp",
        "ticker": "ACME",
        "currency": "USD",
        "period_type": "annual",
        "fiscal_year": 2023,
        "fiscal_period_end": "2023-12-31",
        "units_scale_note": None,
        "items": {
            "revenue": {"value": "1,000,000", "source_page": 1, "confidence": 0.95},
            "cost_of_goods_sold": {"value": "600,000", "source_page": 1, "confidence": 0.9},
            "gross_profit": {"value": "400,000", "source_page": 1, "confidence": 0.9},
            "net_income": {"value": "200,000", "source_page": 1, "confidence": 0.92},
            "shares_outstanding_diluted": {"value": "100,000", "source_page": 1, "confidence": 0.9},
            "total_assets": {"value": "2,000,000", "source_page": 2, "confidence": 0.9},
            "total_liabilities": {"value": "800,000", "source_page": 2, "confidence": 0.9},
            "total_equity": {"value": "1,200,000", "source_page": 2, "confidence": 0.9},
            "total_current_assets": {"value": "900,000", "source_page": 2, "confidence": 0.9},
            "total_current_liabilities": {"value": "400,000", "source_page": 2, "confidence": 0.9},
        },
    }


@pytest.fixture
def e2e(
    client: Any,
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> Any:
    """A TestClient wired so the upload background task hits the in-memory DB.

    Reuses conftest's ``client`` (which overrides ``get_db`` to
    ``session_factory``) and additionally points the background pipeline's own
    ``SessionLocal`` at the same factory plus deterministic OCR/LLM fakes.
    """
    import app.llm.factory as llm_factory
    import app.ocr.factory as ocr_factory

    monkeypatch.setattr(service, "SessionLocal", session_factory)
    monkeypatch.setattr(ocr_factory, "get_ocr_engine", lambda: FakeOCREngine(_income_doc()))
    monkeypatch.setattr(llm_factory, "get_provider", lambda *a, **k: FakeLLMProvider(_payload()))
    monkeypatch.setattr(service.settings, "upload_dir", str(tmp_path))
    return client


def _upload(e2e: Any) -> dict[str, Any]:
    """POST a fake PDF and return the parsed JSON body."""
    resp = e2e.post(
        "/api/documents/upload",
        files={"file": ("acme_10k.pdf", _FAKE_PDF, "application/pdf")},
    )
    assert resp.status_code == 202, resp.text
    return resp.json()


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------


def test_health_ok(e2e: Any) -> None:
    """GET /api/health returns ok and echoes the configured provider."""
    resp = e2e.get("/api/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert "llm_provider" in body


# ---------------------------------------------------------------------------
# Full journey
# ---------------------------------------------------------------------------


def test_full_upload_to_ratios_journey(e2e: Any) -> None:
    """Upload → poll status → read period → correct an item → ratios → validation."""
    # 1) Upload — returns 202 with the new document in 'uploaded' state.
    doc = _upload(e2e)
    doc_id = doc["id"]
    assert doc["filename"] == "acme_10k.pdf"

    # 2) Poll the document. The background task already ran synchronously, so the
    #    status has advanced to needs_review and a period is linked.
    detail = e2e.get(f"/api/documents/{doc_id}")
    assert detail.status_code == 200
    detail_body = detail.json()
    assert detail_body["status"] == "needs_review"
    assert detail_body["num_pages"] == 1
    assert "income_statement" in (detail_body["detected_statement_types"] or [])
    period_id = detail_body["period_id"]
    assert period_id is not None
    # The embedded period carries the extracted, coerced line items.
    assert detail_body["period"]["items"]["revenue"]["value"] == pytest.approx(1_000_000.0)

    # 3) Read the period directly.
    period = e2e.get(f"/api/periods/{period_id}")
    assert period.status_code == 200
    period_body = period.json()
    assert period_body["company_name"] == "Acme Corp"
    assert period_body["fiscal_year"] == 2023
    assert period_body["items"]["net_income"]["value"] == pytest.approx(200_000.0)
    assert period_body["items"]["revenue"]["edited_by_user"] is False

    # 4) Correct a line item via PATCH; it must be flagged edited_by_user.
    patched = e2e.patch(
        f"/api/periods/{period_id}/items",
        json={"updates": {"net_income": 250_000}},
    )
    assert patched.status_code == 200
    patched_body = patched.json()
    assert patched_body["items"]["net_income"]["value"] == pytest.approx(250_000.0)
    assert patched_body["items"]["net_income"]["edited_by_user"] is True

    # 5) Ratios — computed deterministically from the (now corrected) items.
    ratios = e2e.get(f"/api/periods/{period_id}/ratios")
    assert ratios.status_code == 200
    ratios_body = ratios.json()
    assert ratios_body["period_id"] == period_id
    by_key = {r["key"]: r for r in ratios_body["results"]}
    # Net margin uses the corrected net income: 250,000 / 1,000,000 * 100 = 25.0%.
    assert "net_margin" in by_key
    assert by_key["net_margin"]["status"] == "ok"
    assert by_key["net_margin"]["value"] == pytest.approx(25.0)
    # Current ratio = 900,000 / 400,000 = 2.25.
    assert by_key["current_ratio"]["status"] == "ok"
    assert by_key["current_ratio"]["value"] == pytest.approx(2.25)

    # 6) A valuation ratio that needs market data is reported unavailable, not faked.
    pe = by_key["pe_ratio"]
    assert pe["status"] == "unavailable"
    assert pe["value"] is None
    assert "market_price" in pe["missing_inputs"]

    # 7) Validation — accounting identities reconcile (A = L + E, etc.).
    validation = e2e.get(f"/api/periods/{period_id}/validation")
    assert validation.status_code == 200
    val_body = validation.json()
    assert val_body["period_id"] == period_id
    assert val_body["results"]
    assert val_body["summary"].get("ok", 0) >= 1


def test_ratios_unlock_with_market_params(e2e: Any) -> None:
    """Passing market_price + shares_outstanding unlocks valuation ratios."""
    doc = _upload(e2e)
    period_id = e2e.get(f"/api/documents/{doc['id']}").json()["period_id"]

    resp = e2e.get(
        f"/api/periods/{period_id}/ratios",
        params={"market_price": 50.0},
    )
    assert resp.status_code == 200
    by_key = {r["key"]: r for r in resp.json()["results"]}
    pe = by_key["pe_ratio"]
    # EPS = 200,000 / 100,000 = 2.0 → P/E = 50 / 2 = 25.
    assert pe["status"] == "ok"
    assert pe["value"] == pytest.approx(25.0)


# ---------------------------------------------------------------------------
# Company aggregation
# ---------------------------------------------------------------------------


def test_company_listing_and_trend(e2e: Any) -> None:
    """After an upload, the company appears in listings with a ratio trend."""
    _upload(e2e)

    companies = e2e.get("/api/companies")
    assert companies.status_code == 200
    company_list = companies.json()
    assert len(company_list) == 1
    company_id = company_list[0]["id"]
    assert company_list[0]["name"] == "Acme Corp"

    detail = e2e.get(f"/api/companies/{company_id}")
    assert detail.status_code == 200
    assert len(detail.json()["periods"]) == 1

    trend = e2e.get(f"/api/companies/{company_id}/ratios")
    assert trend.status_code == 200
    periods = trend.json()["periods"]
    assert len(periods) == 1
    assert periods[0]["results"]


def test_reupload_same_period_merges(e2e: Any) -> None:
    """Re-uploading the same fiscal period updates in place (no duplicate period)."""
    first = _upload(e2e)
    company_id = (e2e.get(f"/api/documents/{first['id']}").json())["period"]["company_id"]

    # Second upload with identical metadata should reuse the period.
    _upload(e2e)

    detail = e2e.get(f"/api/companies/{company_id}")
    assert detail.status_code == 200
    # Same (company, fiscal_year, period_type) ⇒ one period, not two.
    assert len(detail.json()["periods"]) == 1


# ---------------------------------------------------------------------------
# Error paths
# ---------------------------------------------------------------------------


def test_unknown_period_404(e2e: Any) -> None:
    """Reading a non-existent period returns a clean 404."""
    resp = e2e.get("/api/periods/424242")
    assert resp.status_code == 404


def test_reject_non_pdf_upload(e2e: Any) -> None:
    """A clearly non-PDF content type is rejected with 415."""
    resp = e2e.post(
        "/api/documents/upload",
        files={"file": ("notes.txt", b"hello", "text/plain")},
    )
    assert resp.status_code == 415
