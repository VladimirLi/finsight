"""Extraction service — orchestration and persistence glue.

This module sits between the HTTP layer (API routers) and the OCR + LLM pipeline.
It owns:
  - saving uploaded files to disk with safe, unique names
  - running the end-to-end pipeline (parse → extract → upsert DB) inside a single
    background task, updating Document.status at each transition
  - serialising / deserialising FinancialStatement ↔ FinancialPeriod.statement_json
  - merging incoming extraction results into an existing period while honouring
    human-edited values (edited_by_user=True)
  - applying human corrections from the review UI

All heavy third-party imports (OCR engine, LLM provider, extraction pipeline) are
deferred to inside function bodies so the module is importable with only the core
package installed.
"""

from __future__ import annotations

import logging
import traceback
import uuid
from pathlib import Path
from typing import TYPE_CHECKING, Any

from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.database import SessionLocal
from app.db.models import Company, Document, FinancialPeriod

if TYPE_CHECKING:
    from app.ocr.base import ParsedDocument
from app.schemas.financials import (
    ALL_CANONICAL_FIELDS,
    FinancialStatement,
    FinancialValue,
    StatementType,
)

logger = logging.getLogger(__name__)
settings = get_settings()


# ---------------------------------------------------------------------------
# File storage
# ---------------------------------------------------------------------------


def save_uploaded_file(filename: str, data: bytes, dest_dir: str | None = None) -> str:
    """Write ``data`` bytes to ``dest_dir`` and return the absolute stored path.

    A UUID prefix is prepended to the original filename so concurrent uploads of
    identically named files never collide.  The destination directory is created
    if it does not already exist.

    Args:
        filename: Original client filename (path components are stripped).
        data:     The raw file bytes (the HTTP layer is responsible for reading the
                  upload, since that is async in FastAPI).
        dest_dir: Target directory; defaults to ``settings.upload_dir``. May be
                  relative (resolved to absolute).

    Returns:
        Absolute path string of the saved file.
    """
    dest = Path(dest_dir or settings.upload_dir).resolve()
    dest.mkdir(parents=True, exist_ok=True)

    # Build a safe, collision-proof filename: <uuid>_<original>
    original_name = Path(filename).name  # strip any path components
    safe_name = f"{uuid.uuid4().hex}_{original_name}"
    stored_path = dest / safe_name

    stored_path.write_bytes(data)

    logger.info("Saved upload '%s' → %s (%d bytes)", original_name, stored_path, len(data))
    return str(stored_path)


# ---------------------------------------------------------------------------
# FinancialStatement ↔ DB JSON (de)serialisation helpers
# ---------------------------------------------------------------------------


def get_statement(period: FinancialPeriod) -> FinancialStatement:
    """Deserialise ``period.statement_json`` into a ``FinancialStatement``.

    If the stored JSON is empty or absent a blank statement is returned so
    callers never have to guard against None.
    """
    raw: dict[str, Any] = period.statement_json or {}
    if not raw:
        return FinancialStatement()
    return FinancialStatement.model_validate(raw)


def set_statement(period: FinancialPeriod, statement: FinancialStatement) -> None:
    """Serialise ``statement`` into ``period.statement_json`` (in-place, no commit)."""
    period.statement_json = statement.model_dump(mode="json")


# ---------------------------------------------------------------------------
# Statement merging
# ---------------------------------------------------------------------------


def merge_statements(
    existing: FinancialStatement,
    incoming: FinancialStatement,
) -> FinancialStatement:
    """Merge ``incoming`` extraction results into ``existing``, respecting human edits.

    Rules:
    - Scalar metadata fields (company_name, ticker, currency, period_type,
      fiscal_year, fiscal_period_end, units_scale_note) are taken from ``incoming``
      when non-None, otherwise kept from ``existing``.
    - For each canonical line-item key:
        * If the item in ``existing`` has ``edited_by_user=True`` → keep the human
          value unchanged (the LLM result is ignored for that field).
        * Otherwise → overwrite with the incoming value (even if it is None /
          absent in incoming; a re-extraction that no longer finds a value should
          clear a stale one).
    - Items in ``incoming`` that are not in ALL_CANONICAL_FIELDS are silently dropped.

    Returns a new ``FinancialStatement`` (does not mutate either argument).
    """
    # Merge scalar metadata: prefer incoming non-None values.
    merged_meta: dict[str, Any] = {}
    for field_name in (
        "company_name",
        "ticker",
        "currency",
        "period_type",
        "fiscal_year",
        "fiscal_period_end",
        "units_scale_note",
    ):
        incoming_val = getattr(incoming, field_name, None)
        existing_val = getattr(existing, field_name, None)
        merged_meta[field_name] = incoming_val if incoming_val is not None else existing_val

    # Merge line items.
    merged_items: dict[str, FinancialValue] = {}

    for key in ALL_CANONICAL_FIELDS:
        existing_fv: FinancialValue | None = existing.items.get(key)
        incoming_fv: FinancialValue | None = incoming.items.get(key)

        if existing_fv is not None and existing_fv.edited_by_user:
            # Human-edited value wins unconditionally.
            merged_items[key] = existing_fv
        elif incoming_fv is not None:
            # Fresh extraction result (not human-edited).
            merged_items[key] = incoming_fv
        elif existing_fv is not None:
            # No new data from extraction; retain what was already stored.
            merged_items[key] = existing_fv
        # else: nothing from either side — leave the key absent.

    return FinancialStatement(items=merged_items, **merged_meta)


# ---------------------------------------------------------------------------
# Item-level human corrections
# ---------------------------------------------------------------------------


def apply_item_updates(
    db: Session,
    period: FinancialPeriod,
    updates: dict[str, float | None],
) -> FinancialPeriod:
    """Apply human corrections from the review UI to a period.

    For each key in ``updates``:
      - The numeric value (or None) is written to the canonical item.
      - ``edited_by_user`` is set to True unconditionally.

    Unknown canonical keys are silently ignored so the API stays forward-compatible.

    Commits the session before returning.

    Args:
        db:      Active SQLAlchemy session.
        period:  The ``FinancialPeriod`` row to update.
        updates: Mapping of canonical key → new value (None clears the value but
                 still marks it as human-reviewed).

    Returns:
        The updated (and committed) ``FinancialPeriod`` instance.
    """
    statement = get_statement(period)

    for key, new_value in updates.items():
        if key not in ALL_CANONICAL_FIELDS:
            logger.debug("apply_item_updates: ignoring unknown key '%s'", key)
            continue

        existing_fv: FinancialValue | None = statement.items.get(key)
        if existing_fv is not None:
            # Preserve provenance, override value + edited flag.
            statement.items[key] = existing_fv.model_copy(
                update={"value": new_value, "edited_by_user": True}
            )
        else:
            statement.items[key] = FinancialValue(value=new_value, edited_by_user=True)

    set_statement(period, statement)
    db.commit()
    db.refresh(period)
    return period


# ---------------------------------------------------------------------------
# Company / period upsert helpers (internal)
# ---------------------------------------------------------------------------


def _upsert_company(db: Session, statement: FinancialStatement) -> Company:
    """Find or create a Company from the extracted statement metadata.

    Match strategy: exact (case-insensitive) name match first; if a ticker is
    present it must also match.  New records are added + flushed (not committed)
    so the caller controls the transaction boundary.
    """
    name: str = (statement.company_name or "").strip()
    ticker: str | None = (statement.ticker or "").strip() or None

    query = db.query(Company)
    if name:
        query = query.filter(Company.name.ilike(name))
    if ticker:
        query = query.filter(Company.ticker.ilike(ticker))

    company: Company | None = query.first()

    if company is None:
        company = Company(
            name=name or "Unknown",
            ticker=ticker,
            currency=statement.currency,
        )
        db.add(company)
        db.flush()  # populate company.id without committing
        logger.info("Created new Company id=%d name='%s'", company.id, company.name)
    else:
        # Update ticker / currency if extraction filled them in.
        if ticker and company.ticker is None:
            company.ticker = ticker
        if statement.currency and company.currency is None:
            company.currency = statement.currency

    return company


def _upsert_period(
    db: Session,
    company: Company,
    statement: FinancialStatement,
) -> FinancialPeriod:
    """Find or create a FinancialPeriod and merge the new statement into it.

    Match key: (company_id, fiscal_year, period_type).  If ``fiscal_year`` is
    None a new period is always created (we cannot deduplicate without a year).
    """
    period_type_val: str | None = statement.period_type.value if statement.period_type else None
    fiscal_year_val: int | None = statement.fiscal_year

    existing_period: FinancialPeriod | None = None
    if fiscal_year_val is not None:
        existing_period = (
            db.query(FinancialPeriod)
            .filter(
                FinancialPeriod.company_id == company.id,
                FinancialPeriod.fiscal_year == fiscal_year_val,
                FinancialPeriod.period_type == period_type_val,
            )
            .first()
        )

    if existing_period is None:
        existing_period = FinancialPeriod(
            company_id=company.id,
            period_type=period_type_val,
            fiscal_year=fiscal_year_val,
            fiscal_period_end=statement.fiscal_period_end,
            currency=statement.currency,
            statement_json={},
        )
        db.add(existing_period)
        db.flush()
        logger.info(
            "Created new FinancialPeriod id=%d company_id=%d year=%s type=%s",
            existing_period.id,
            company.id,
            fiscal_year_val,
            period_type_val,
        )

    # Update metadata that may have been absent on initial creation.
    if statement.fiscal_period_end and not existing_period.fiscal_period_end:
        existing_period.fiscal_period_end = statement.fiscal_period_end
    if statement.currency and not existing_period.currency:
        existing_period.currency = statement.currency

    # Merge new extraction results while preserving human edits.
    old_statement = get_statement(existing_period)
    merged = merge_statements(old_statement, statement)
    set_statement(existing_period, merged)

    return existing_period


# ---------------------------------------------------------------------------
# Main pipeline runner
# ---------------------------------------------------------------------------


def process_document(document_id: int, company_id: int | None = None) -> None:
    """Run the full OCR → LLM extraction → DB persistence pipeline for one document.

    This is invoked as a FastAPI background task *after* the request has returned, so
    it owns its own database session rather than reusing the (closed) request-scoped
    one.

    Status transitions (written to DB between each step so failure is visible):
        uploaded → parsing → extracting → needs_review
                                        ↘ failed  (on any exception)

    The function never raises; all exceptions are caught, written to
    ``Document.error``, and the status is set to ``"failed"``.

    Args:
        document_id: Primary key of the ``Document`` row to process.
        company_id:  If provided, the resulting period is attached to this existing
                     company instead of upserting one from the extracted name/ticker.
    """
    db = SessionLocal()
    try:
        _run_pipeline(db, document_id, company_id)
    finally:
        db.close()


def _run_pipeline(db: Session, document_id: int, company_id: int | None) -> None:
    # ------------------------------------------------------------------ fetch
    document: Document | None = db.get(Document, document_id)
    if document is None:
        logger.error("process_document: Document id=%d not found", document_id)
        return

    def _fail(msg: str) -> None:
        """Transition document to failed state."""
        document.status = "failed"
        document.error = msg
        db.commit()
        logger.error("Document id=%d failed: %s", document_id, msg)

    stored_path: str = document.stored_path

    # ------------------------------------------------------------------ step 1: parse
    try:
        document.status = "parsing"
        document.error = None
        db.commit()

        # Lazy import — keeps this module importable without OCR dependencies.
        from app.ocr.factory import get_ocr_engine

        ocr_engine = get_ocr_engine()
        parsed_doc = ocr_engine.parse(stored_path)

        document.num_pages = parsed_doc.num_pages

        # Detect which statement types appear in the document by scanning page text.
        detected: list[str] = _detect_statement_types(parsed_doc)
        document.detected_statement_types = detected or None

        db.commit()
        logger.info(
            "Document id=%d parsed: %d pages, types=%s",
            document_id,
            parsed_doc.num_pages,
            detected,
        )
    except Exception:
        _fail(f"Parsing failed:\n{traceback.format_exc()}")
        return

    # ------------------------------------------------------------------ step 2: extract
    try:
        document.status = "extracting"
        db.commit()

        # Lazy imports — heavy deps live here.
        from app.extraction.pipeline import extract_statement
        from app.llm.factory import get_provider

        llm_provider = get_provider()
        statement: FinancialStatement = extract_statement(
            doc=parsed_doc,
            provider=llm_provider,
            model=settings.llm_model,
        )

        logger.info(
            "Document id=%d extraction complete: company='%s' year=%s",
            document_id,
            statement.company_name,
            statement.fiscal_year,
        )
    except Exception:
        _fail(f"Extraction failed:\n{traceback.format_exc()}")
        return

    # ------------------------------------------------------------------ step 3: persist
    try:
        if company_id is not None:
            existing = db.get(Company, company_id)
            if existing is None:
                _fail(f"company_id={company_id} not found")
                return
            company = existing
        else:
            company = _upsert_company(db, statement)
        period = _upsert_period(db, company, statement)

        document.period_id = period.id
        document.status = "needs_review"
        document.error = None
        db.commit()

        logger.info(
            "Document id=%d → period id=%d, status=needs_review",
            document_id,
            period.id,
        )
    except Exception:
        _fail(f"Persistence failed:\n{traceback.format_exc()}")
        return


# ---------------------------------------------------------------------------
# Internal utilities
# ---------------------------------------------------------------------------

# Keywords used to identify which financial statement types appear in a document.
# Keys are taken from StatementType enum values so the enum is genuinely used.
_STATEMENT_KEYWORDS: dict[str, list[str]] = {
    StatementType.income_statement.value: [
        "revenue",
        "net income",
        "earnings per share",
        "gross profit",
        "operating income",
        "income from operations",
        "statement of operations",
        "income statement",
        "profit and loss",
    ],
    StatementType.balance_sheet.value: [
        "total assets",
        "total liabilities",
        "shareholders' equity",
        "stockholders' equity",
        "balance sheet",
        "statement of financial position",
        "current assets",
        "current liabilities",
    ],
    StatementType.cash_flow.value: [
        "operating activities",
        "investing activities",
        "financing activities",
        "cash flow",
        "cash flows",
        "free cash flow",
        "capital expenditure",
    ],
}


def _detect_statement_types(parsed_doc: ParsedDocument) -> list[str]:
    """Heuristically identify which statement types appear in the parsed document.

    Scans the combined full text for a small set of distinctive keywords.
    Returns a list of statement type strings (subset of the StatementType enum values).
    """
    full_text: str = parsed_doc.full_text().lower()
    detected: list[str] = []
    for stmt_type, keywords in _STATEMENT_KEYWORDS.items():
        if any(kw in full_text for kw in keywords):
            detected.append(stmt_type)
    return detected
