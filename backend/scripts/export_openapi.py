"""Export the FastAPI OpenAPI schema to a JSON file.

Usage:
    # As a script (default output path):
    python scripts/export_openapi.py

    # As a script (custom output path):
    python scripts/export_openapi.py /path/to/openapi.json

    # As a module:
    python -m scripts.export_openapi
    python -m scripts.export_openapi /path/to/openapi.json
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Allow running from repo root or from the backend directory.
_BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

_DEFAULT_OUTPUT = _BACKEND_DIR / "openapi.json"


def export(output_path: Path | None = None) -> Path:
    """Generate the OpenAPI schema and write it to *output_path*.

    Args:
        output_path: Destination file.  Defaults to
            ``<backend-root>/openapi.json``.

    Returns:
        The resolved path of the written file.
    """
    from app.main import app  # noqa: PLC0415 — intentional late import

    resolved = (output_path or _DEFAULT_OUTPUT).resolve()
    schema = app.openapi()
    resolved.write_text(
        json.dumps(schema, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return resolved


def main() -> None:
    """CLI entry point."""
    output_path: Path | None = None
    if len(sys.argv) > 1:
        output_path = Path(sys.argv[1])

    written = export(output_path)
    print(f"OpenAPI schema written to: {written}")


if __name__ == "__main__":
    main()
