"""Shared test fixtures for deterministic extraction / persistence tests.

Nothing here touches the network, a real LLM, or the real on-disk SQLite DB.

Provides:
  * ``FakeLLMProvider`` — an :class:`~app.llm.base.LLMProvider` whose
    ``complete()`` / ``extract_json()`` return a canned payload supplied at
    construction, so a test controls exactly what the "model" returns.
  * ``FakeOCREngine`` — an :class:`~app.ocr.base.OCREngine` returning a
    pre-built :class:`~app.ocr.base.ParsedDocument`.
  * ``build_parsed_document`` — a helper to assemble a ``ParsedDocument`` from
    plain page text / table rows.
  * ``in_memory_db`` — an in-memory SQLite engine + Session factory (schema
    created once, never the real ``finsight.db``).
  * ``client`` — a FastAPI ``TestClient`` with ``get_db`` overridden to the
    in-memory session.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any, override

import pytest
from app.db.database import Base, get_db
from app.llm.base import LLMProvider, LLMResponse
from app.ocr.base import OCREngine, Page, ParsedDocument, Table
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

# ---------------------------------------------------------------------------
# Fake LLM provider
# ---------------------------------------------------------------------------


class FakeLLMProvider(LLMProvider):
    """An ``LLMProvider`` that returns a fixed, test-controlled payload.

    The ``payload`` passed at construction is returned verbatim as
    ``LLMResponse.parsed`` from :meth:`extract_json` (and serialised into
    ``content`` for :meth:`complete`). This makes the parse -> extract path
    fully deterministic.
    """

    name = "fake"

    def __init__(self, payload: dict[str, Any], *, content: str = "") -> None:
        self._payload = payload
        self._content = content

    @override
    def complete(
        self,
        *,
        system: str | None,
        prompt: str,
        model: str,
        max_tokens: int = 4096,
        temperature: float = 0.0,
    ) -> LLMResponse:
        return LLMResponse(content=self._content or prompt, model=model)

    @override
    def extract_json(
        self,
        *,
        system: str | None,
        prompt: str,
        json_schema: dict[str, Any],
        model: str,
        max_tokens: int = 4096,
        temperature: float = 0.0,
    ) -> LLMResponse:
        return LLMResponse(
            content=self._content,
            parsed=self._payload,
            model=model,
        )


# ---------------------------------------------------------------------------
# Fake OCR engine + ParsedDocument builder
# ---------------------------------------------------------------------------


def build_parsed_document(
    *,
    filename: str = "test.pdf",
    pages: list[tuple[str, list[list[str]]]] | None = None,
) -> ParsedDocument:
    """Build a :class:`ParsedDocument` from ``(text, table_rows)`` per page.

    Args:
        filename: Document filename.
        pages:    One ``(page_text, table_rows)`` tuple per page, where
                  ``table_rows`` is a row-major list of stringified cells.
                  When ``None`` a single empty page is created.

    Returns:
        A fully-formed ``ParsedDocument`` with 1-based page numbers.
    """
    page_specs = pages if pages is not None else [("", [])]
    built_pages: list[Page] = []
    for idx, (text, table_rows) in enumerate(page_specs, start=1):
        tables: list[Table] = []
        if table_rows:
            tables.append(Table(page=idx, rows=table_rows))
        built_pages.append(Page(number=idx, text=text, tables=tables))
    return ParsedDocument(
        filename=filename,
        pages=built_pages,
        num_pages=len(built_pages),
    )


class FakeOCREngine(OCREngine):
    """An ``OCREngine`` that ignores the path and returns a canned document."""

    def __init__(self, doc: ParsedDocument) -> None:
        self._doc = doc

    @override
    def parse(self, file_path: str) -> ParsedDocument:
        return self._doc


# ---------------------------------------------------------------------------
# In-memory DB + FastAPI app factory
# ---------------------------------------------------------------------------


@pytest.fixture
def session_factory() -> Iterator[sessionmaker[Session]]:
    """An in-memory SQLite Session factory with the full schema created.

    A ``StaticPool`` keeps a single shared in-memory connection so every
    session in a test sees the same database. The real ``finsight.db`` file is
    never touched.
    """
    # Importing models registers them on ``Base.metadata`` for ``create_all``.
    from app.db import models  # noqa: F401

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    try:
        yield factory
    finally:
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


@pytest.fixture
def db_session(session_factory: sessionmaker[Session]) -> Iterator[Session]:
    """A single in-memory ``Session`` for direct (non-API) use in a test."""
    session = session_factory()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client(session_factory: sessionmaker[Session]) -> Iterator[Any]:
    """A FastAPI ``TestClient`` with ``get_db`` overridden to in-memory SQLite."""
    from app.main import app
    from fastapi.testclient import TestClient

    def _override_get_db() -> Iterator[Session]:
        session = session_factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = _override_get_db
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.pop(get_db, None)
