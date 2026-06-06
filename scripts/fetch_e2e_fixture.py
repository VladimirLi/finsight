#!/usr/bin/env python3
"""Fetch a REAL company financial filing and slice out the statement pages.

The Playwright extraction spec uploads this fixture and lets the genuine OCR +
Ollama pipeline extract it, so it must be a real document with a real text layer
and recognisable financial statements — not a synthetic mock.

Source: a publicly available annual report PDF (Berkshire Hathaway by default —
a stable, long-lived URL whose report contains clean consolidated statements).
The full report is ~140 pages; uploading all of it would make the local-model
extraction painfully slow, so we keep only the consolidated balance sheet and
statements of earnings pages. The result is still genuine real-company data.

The fixture is intentionally NOT committed (it is third-party copyrighted
material); it is fetched on demand and git-ignored. The extraction spec
self-skips when it is absent.

Usage:
    backend/.venv/bin/python scripts/fetch_e2e_fixture.py

Env:
    E2E_FIXTURE_URL   override the source PDF URL
    E2E_FIXTURE_OUT   override the output path
"""

from __future__ import annotations

import os
import sys
import urllib.request
from pathlib import Path

import fitz  # PyMuPDF

# Berkshire Hathaway's annual report — a stable public URL with real, clean
# consolidated financial statements.
_DEFAULT_URL = "https://www.berkshirehathaway.com/2023ar/2023ar.pdf"
_DEFAULT_OUT = (
    Path(__file__).resolve().parent.parent
    / "frontend"
    / "e2e"
    / "fixtures"
    / "real-financials.pdf"
)
# A descriptive UA is polite (and required by some hosts, e.g. SEC EDGAR).
_USER_AGENT = "finsight-e2e-tests (+https://github.com/VladimirLi/finsight)"

# Headers that mark the financial-statement pages we want to keep. The titles
# sit at the top of each statement page (matched against the first few lines).
_WANTED_HEADERS = (
    "CONSOLIDATED BALANCE SHEET",
    "CONSOLIDATED STATEMENTS OF EARNINGS",
    "CONSOLIDATED STATEMENT OF EARNINGS",
    "CONSOLIDATED STATEMENTS OF OPERATIONS",
    "CONSOLIDATED STATEMENTS OF COMPREHENSIVE",
    "CONSOLIDATED STATEMENTS OF CASH FLOWS",
)
# Running headers on prose pages (e.g. MD&A) also name the statements; exclude
# those so we keep only the actual statement tables.
_EXCLUDE_MARKERS = ("MANAGEMENT", "TABLE OF CONTENTS", "NOTES TO")
_TOP_LINES = 6  # statement titles appear within the first few non-empty lines
_MAX_PAGES = 6  # keep the upload (and local-model run) small


def _download(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})  # noqa: S310
    with urllib.request.urlopen(req, timeout=60) as resp:  # noqa: S310
        return resp.read()


def _statement_pages(doc: fitz.Document) -> list[int]:
    """Return the indices of pages whose top is a financial-statement title.

    Matches the statement title against the first few non-empty lines (the title
    sits at the page top) and skips prose pages whose running header merely names
    a statement (MD&A, table of contents).
    """
    hits: list[int] = []
    for i in range(doc.page_count):
        lines = [ln.strip() for ln in doc[i].get_text().splitlines() if ln.strip()]
        top = " ".join(lines[:_TOP_LINES]).upper()
        if any(m in top for m in _EXCLUDE_MARKERS):
            continue
        if any(h in top for h in _WANTED_HEADERS):
            hits.append(i)
    return hits[:_MAX_PAGES]


def main() -> int:
    url = os.environ.get("E2E_FIXTURE_URL", _DEFAULT_URL)
    out = Path(os.environ.get("E2E_FIXTURE_OUT", str(_DEFAULT_OUT)))
    out.parent.mkdir(parents=True, exist_ok=True)

    print(f"Downloading real filing: {url}")
    raw = _download(url)
    src = fitz.open(stream=raw, filetype="pdf")
    print(f"  fetched {len(raw):,} bytes, {src.page_count} pages")

    pages = _statement_pages(src)
    if not pages:
        print(
            "ERROR: no financial-statement pages found — the source layout may "
            "have changed. Set E2E_FIXTURE_URL to a different filing.",
            file=sys.stderr,
        )
        return 1

    out_doc = fitz.open()
    for i in pages:
        out_doc.insert_pdf(src, from_page=i, to_page=i)
    out_doc.save(str(out), garbage=4, deflate=True)
    out_doc.close()
    src.close()

    size = out.stat().st_size
    print(f"Wrote {len(pages)} real statement pages → {out} ({size:,} bytes)")
    print(f"  source pages (0-based): {pages}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
