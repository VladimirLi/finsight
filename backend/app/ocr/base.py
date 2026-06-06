"""OCR / document-parsing interface.

Financial statements are tables. Plain text extraction mangles them, so the OCR
layer returns BOTH page text and structured tables, with page numbers preserved so
extracted values can cite their source page.

The default engine (app/ocr/engine.py) uses PyMuPDF for born-digital PDFs and
falls back to an OCR engine (pytesseract over rendered page images) for scanned
pages. Table structure is recovered with pdfplumber / camelot where possible.
"""

from __future__ import annotations

import abc
from dataclasses import dataclass, field


@dataclass
class Table:
    """A recovered table on a page, as row-major stringified cells."""

    page: int
    rows: list[list[str]]  # row-major cells, already stringified
    bbox: tuple[float, float, float, float] | None = None

    def to_markdown(self) -> str:
        """Render the table rows as a pipe-delimited markdown block."""
        if not self.rows:
            return ""
        return "\n".join(" | ".join(c or "" for c in row) for row in self.rows)


@dataclass
class Page:
    """A single parsed page: text plus any recovered tables."""

    number: int  # 1-based
    text: str = ""
    tables: list[Table] = field(default_factory=list)
    is_scanned: bool = False  # True if OCR (rather than embedded text) was used


@dataclass
class ParsedDocument:
    """A fully parsed document: an ordered list of pages."""

    filename: str
    pages: list[Page] = field(default_factory=list)
    num_pages: int = 0

    def full_text(self) -> str:
        """Return all page text concatenated with page markers."""
        return "\n\n".join(f"[Page {p.number}]\n{p.text}" for p in self.pages)

    def all_tables_markdown(self) -> str:
        """Return every page table rendered as markdown, page-labelled."""
        chunks: list[str] = []
        for p in self.pages:
            for t in p.tables:
                chunks.append(f"[Page {p.number} table]\n{t.to_markdown()}")
        return "\n\n".join(chunks)


class OCREngine(abc.ABC):
    """Abstract document parser returning pages with text and tables."""

    @abc.abstractmethod
    def parse(self, file_path: str) -> ParsedDocument:
        """Parse a PDF (or image) into pages with text + tables."""
