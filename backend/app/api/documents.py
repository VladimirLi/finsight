"""Document CRUD endpoints.

GET  /documents          → Document[]
GET  /documents/{id}     → DocumentDetail
POST /documents/{id}/reprocess → Document  (re-run extraction pipeline)
DELETE /documents/{id}   → { ok: true }
"""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload

from app.api._hydrate import period_to_detail
from app.api.serializers import (
    DocumentDetailOut,
    DocumentOut,
    OkOut,
    PeriodDetailOut,
)
from app.db.database import get_db
from app.db.models import Document, FinancialPeriod

router = APIRouter()


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _doc_to_out(doc: Document) -> DocumentOut:
    return DocumentOut(
        id=doc.id,
        filename=doc.filename,
        status=doc.status,
        num_pages=doc.num_pages,
        error=doc.error,
        detected_statement_types=doc.detected_statement_types,
        period_id=doc.period_id,
        created_at=doc.created_at.isoformat(),
    )


def _doc_to_detail(doc: Document) -> DocumentDetailOut:
    period_out: PeriodDetailOut | None = None
    if doc.period is not None:
        period_out = period_to_detail(doc.period)
    return DocumentDetailOut(
        id=doc.id,
        filename=doc.filename,
        status=doc.status,
        num_pages=doc.num_pages,
        error=doc.error,
        detected_statement_types=doc.detected_statement_types,
        period_id=doc.period_id,
        created_at=doc.created_at.isoformat(),
        period=period_out,
    )


def _get_doc_or_404(db: Session, doc_id: int) -> Document:
    doc = (
        db.query(Document)
        .options(joinedload(Document.period).joinedload(FinancialPeriod.company))
        .filter(Document.id == doc_id)
        .first()
    )
    if doc is None:
        raise HTTPException(status_code=404, detail=f"Document {doc_id} not found.")
    return doc


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("/documents", response_model=list[DocumentOut])
def list_documents(db: Session = Depends(get_db)) -> list[DocumentOut]:
    """Return all documents ordered newest-first."""
    docs = db.query(Document).order_by(Document.id.desc()).all()
    return [_doc_to_out(d) for d in docs]


@router.get("/documents/{doc_id}", response_model=DocumentDetailOut)
def get_document(doc_id: int, db: Session = Depends(get_db)) -> DocumentDetailOut:
    """Return a document with its associated period and line items."""
    doc = _get_doc_or_404(db, doc_id)
    return _doc_to_detail(doc)


@router.post("/documents/{doc_id}/reprocess", response_model=DocumentOut, status_code=202)
def reprocess_document(
    doc_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> DocumentOut:
    """Reset the document to 'uploaded' status and re-run the extraction pipeline.

    Useful after the user has corrected OCR settings or the provider configuration
    has changed.
    """
    # Lazy import keeps the app importable without extraction deps.
    from app.extraction import service as extraction_service  # noqa: PLC0415

    doc = _get_doc_or_404(db, doc_id)

    # Reset pipeline state so the UI reflects that processing has restarted.
    doc.status = "uploaded"
    doc.error = None
    db.commit()
    db.refresh(doc)

    background_tasks.add_task(
        extraction_service.process_document,
        document_id=doc.id,
        company_id=doc.period.company_id if doc.period is not None else None,
    )

    return _doc_to_out(doc)


@router.delete("/documents/{doc_id}", response_model=OkOut)
def delete_document(doc_id: int, db: Session = Depends(get_db)) -> OkOut:
    """Hard-delete a document record (does NOT remove the file from disk)."""
    doc = _get_doc_or_404(db, doc_id)
    db.delete(doc)
    db.commit()
    return OkOut(ok=True)
