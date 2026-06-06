"""Drift check: every Settings field must be documented in .env.example.

If someone adds a field to ``app.config.Settings`` but forgets to document the
corresponding environment variable in ``.env.example``, this test fails — keeping
the example file in sync with the actual configuration surface. Commented-out keys
(``# FOO=...``) count as documented.
"""

from __future__ import annotations

import re
from pathlib import Path

from app.config import Settings

_ENV_EXAMPLE = Path(__file__).resolve().parent.parent / ".env.example"
_KEY_RE = re.compile(r"^\s*#?\s*([A-Z][A-Z0-9_]*)\s*=")


def _documented_keys() -> set[str]:
    keys: set[str] = set()
    for line in _ENV_EXAMPLE.read_text().splitlines():
        match = _KEY_RE.match(line)
        if match:
            keys.add(match.group(1))
    return keys


def test_every_setting_is_documented_in_env_example() -> None:
    documented = _documented_keys()
    setting_envs = {name.upper() for name in Settings.model_fields}
    missing = setting_envs - documented
    assert not missing, (
        f"Settings fields missing from .env.example: {sorted(missing)}. "
        "Add them (commented is fine) so the example stays in sync with config."
    )
