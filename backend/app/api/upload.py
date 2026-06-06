"""POST /documents/upload — receive a PDF, persist it, kick off async pipeline."""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.api.serializers import DocumentOut
from app.db.database import get_db
from app.db.models import Document

router = APIRouter()


def _doc_to_out(doc: Document) -> DocumentOut:
    """Convert a Document ORM row to the API response shape."""
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


@router.post("/documents/upload", response_model=DocumentOut, status_code=202)
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    company_id: int | None = Form(default=None),
    db: Session = Depends(get_db),
) -> DocumentOut:
    """Accept a PDF upload and queue the extraction pipeline.

    Stores the file on disk, creates a ``Document`` row, and schedules the
    extraction pipeline as a background task.

    Returns HTTP 202 (Accepted) immediately; the client polls
    GET /documents/{id} to watch ``status`` transition through the pipeline stages:
        uploaded → parsing → extracting → needs_review | ready | failed
    """
    # Lazy import so the app starts even without heavy extraction deps installed.
    from app.extraction import service as extraction_service  # noqa: PLC0415

    # Validate content type before writing to disk. Accept octet-stream and None for
    # clients that don't set the type correctly; only reject clearly non-PDF types.
    if (
        file.content_type not in ("application/pdf", "application/octet-stream", None)
        and file.content_type
        and not file.content_type.startswith("application/")
    ):
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported media type '{file.content_type}'. Upload a PDF.",
        )

    # Read the uploaded bytes and persist the file to the upload directory.
    file_bytes = await file.read()
    stored_path = extraction_service.save_uploaded_file(
        filename=file.filename or "upload.pdf",
        data=file_bytes,
    )

    # Create the DB record immediately so the client has an ID to poll.
    doc = Document(
        filename=file.filename or "upload.pdf",
        stored_path=stored_path,
        status="uploaded",
        period_id=None,  # pipeline may link to a period after extraction
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)

    # Queue the extraction pipeline; do NOT await — return immediately.
    background_tasks.add_task(
        extraction_service.process_document,
        document_id=doc.id,
        company_id=company_id,
    )

    return _doc_to_out(doc)
