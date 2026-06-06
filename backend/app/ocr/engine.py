"""Default OCR engine implementation.

Strategy:
  1. Detect file type by extension.
  2. For PDFs — open with PyMuPDF (fitz) and iterate pages:
       a. Extract embedded text via page.get_text("text").
       b. If the page yields fewer than MIN_TEXT_CHARS characters, treat it as
          scanned: render to a PIL Image at settings.ocr_dpi and run pytesseract.
       c. Extract tables with pdfplumber (page.extract_tables()).
  3. For images (.png / .jpg / .jpeg) — single page via pytesseract directly.
  4. Per-page failures are caught and logged; they do not abort the whole document.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, cast, override

from app.ocr.base import OCREngine, Page, ParsedDocument, Table

logger = logging.getLogger(__name__)

# Pages with fewer embedded characters than this threshold are treated as scanned.
_MIN_TEXT_CHARS = 50

# Image extensions that the engine handles directly (single-page OCR).
_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".tiff", ".bmp", ".gif", ".webp"}


class DefaultOCREngine(OCREngine):
    """Default OCR engine.

    Combines PyMuPDF text extraction, pytesseract OCR, and pdfplumber table
    extraction.
    """

    @override
    def parse(self, file_path: str) -> ParsedDocument:
        """Parse a PDF or image file into a :class:`ParsedDocument`.

        Parameters
        ----------
        file_path:
            Absolute or relative path to the file on disk.

        Returns:
        -------
        ParsedDocument
            Populated with per-page text, tables, and scanned flag.
        """
        path = Path(file_path)
        filename = path.name
        suffix = path.suffix.lower()

        if suffix in _IMAGE_EXTENSIONS:
            return self._parse_image(file_path, filename)

        # Default: treat as PDF.
        return self._parse_pdf(file_path, filename)

    # ------------------------------------------------------------------
    # PDF handling
    # ------------------------------------------------------------------

    def _parse_pdf(self, file_path: str, filename: str) -> ParsedDocument:
        """Open the PDF with PyMuPDF and iterate over every page."""
        # Lazy imports — not at module level so the app boots without these packages.
        import fitz  # PyMuPDF

        from app.config import get_settings

        settings = get_settings()

        doc = fitz.open(file_path)
        num_pages = doc.page_count

        parsed = ParsedDocument(filename=filename, num_pages=num_pages)

        # Open the same file with pdfplumber for table extraction.
        # We keep one pdfplumber document open for the whole file to avoid
        # re-opening it on every page.
        plumber_doc = self._open_pdfplumber(file_path)

        try:
            for page_index in range(num_pages):
                page_number = page_index + 1  # 1-based
                try:
                    page = self._process_pdf_page(
                        doc=doc,
                        plumber_doc=plumber_doc,
                        page_index=page_index,
                        page_number=page_number,
                        settings=settings,
                    )
                    parsed.pages.append(page)
                except Exception as exc:
                    logger.warning(
                        "Failed to process page %d of %s: %s",
                        page_number,
                        filename,
                        exc,
                        exc_info=True,
                    )
                    # Append an empty placeholder page so page numbering stays intact.
                    parsed.pages.append(Page(number=page_number, text="", is_scanned=False))
        finally:
            doc.close()
            if plumber_doc is not None:
                plumber_doc.close()

        return parsed

    def _process_pdf_page(
        self,
        doc: Any,
        plumber_doc: Any,
        page_index: int,
        page_number: int,
        settings: Any,
    ) -> Page:
        """Extract text and tables from a single PDF page."""
        fitz_page = doc[page_index]

        # --- Embedded text ---
        text = fitz_page.get_text("text").strip()
        is_scanned = False

        if len(text) < _MIN_TEXT_CHARS:
            # Too little embedded text — fall back to OCR.
            is_scanned = True
            text = self._ocr_fitz_page(fitz_page, settings)

        # --- Tables via pdfplumber ---
        tables: list[Table] = []
        if plumber_doc is not None:
            try:
                plumber_page = plumber_doc.pages[page_index]
                raw_tables = plumber_page.extract_tables() or []
                for raw_table in raw_tables:
                    rows = self._stringify_table(raw_table)
                    if rows:
                        tables.append(Table(page=page_number, rows=rows))
            except Exception as exc:
                logger.warning("pdfplumber failed on page %d: %s", page_number, exc, exc_info=True)

        return Page(number=page_number, text=text, tables=tables, is_scanned=is_scanned)

    # ------------------------------------------------------------------
    # Image handling
    # ------------------------------------------------------------------

    def _parse_image(self, file_path: str, filename: str) -> ParsedDocument:
        """OCR a standalone image file and wrap it in a single-page document."""
        from app.config import get_settings

        settings = get_settings()

        text = self._ocr_image_path(file_path, settings)
        page = Page(number=1, text=text, tables=[], is_scanned=True)
        return ParsedDocument(filename=filename, pages=[page], num_pages=1)

    # ------------------------------------------------------------------
    # OCR helpers
    # ------------------------------------------------------------------

    def _ocr_fitz_page(self, fitz_page: Any, settings: Any) -> str:
        """Render a PyMuPDF page to a PIL Image and OCR it with pytesseract."""
        import pytesseract
        from PIL import Image

        if settings.tesseract_cmd:
            pytesseract.pytesseract.tesseract_cmd = settings.tesseract_cmd

        # Build a transformation matrix from the desired DPI.
        # PyMuPDF's default resolution is 72 DPI; scale factor = dpi / 72.
        import fitz

        scale = settings.ocr_dpi / 72.0
        mat = fitz.Matrix(scale, scale)

        # Render to a pixmap and then convert to PIL Image.
        pix = fitz_page.get_pixmap(matrix=mat, alpha=False)
        img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)

        # image_to_string returns str with the default output type; cast narrows the
        # stub's bytes|str|dict union (pyright sees the real types once pytesseract is installed).
        text = cast(str, pytesseract.image_to_string(img))
        return text.strip()

    def _ocr_image_path(self, file_path: str, settings: Any) -> str:
        """Run pytesseract on an image file given its path."""
        import pytesseract
        from PIL import Image

        if settings.tesseract_cmd:
            pytesseract.pytesseract.tesseract_cmd = settings.tesseract_cmd

        img = Image.open(file_path)
        # image_to_string returns str with the default output type; cast narrows the
        # stub's bytes|str|dict union (pyright sees the real types once pytesseract is installed).
        text = cast(str, pytesseract.image_to_string(img))
        return text.strip()

    # ------------------------------------------------------------------
    # pdfplumber helpers
    # ------------------------------------------------------------------

    def _open_pdfplumber(self, file_path: str) -> Any:
        """Open file_path with pdfplumber; return None on failure."""
        try:
            import pdfplumber

            return pdfplumber.open(file_path)
        except Exception as exc:
            logger.warning("pdfplumber could not open %s: %s", file_path, exc)
            return None

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------

    @staticmethod
    def _stringify_table(raw_table: list[list[Any]]) -> list[list[str]]:
        """Convert a pdfplumber raw table to a list of string rows.

        ``None`` cells are replaced with the empty string.
        """
        result: list[list[str]] = []
        for row in raw_table:
            str_row = [cell if cell is not None else "" for cell in row]
            # Ensure every cell is a str (pdfplumber occasionally returns numbers).
            str_row = [str(cell) for cell in str_row]
            result.append(str_row)
        return result
