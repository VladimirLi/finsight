"""OCR engine factory.

Returns the default OCR engine. All third-party imports remain lazy (inside
DefaultOCREngine methods) so the factory itself can be imported without any
OCR libraries installed.
"""

from __future__ import annotations

from app.ocr.base import OCREngine


def get_ocr_engine() -> OCREngine:
    """Return the configured OCR engine instance.

    Currently always returns :class:`~app.ocr.engine.DefaultOCREngine`.
    The import of the concrete implementation is deferred to this function
    so the module graph stays lightweight at startup.
    """
    from app.ocr.engine import DefaultOCREngine  # lazy — keeps top-level imports clean

    return DefaultOCREngine()
