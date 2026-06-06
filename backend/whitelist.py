# whitelist.py — vulture false-positive suppression
#
# This file contains entries for names that vulture flags as unused but are
# genuine framework/interface requirements, not dead code:
#
#   updated_at       — SQLAlchemy column automatically updated by the DB layer.
#   _.complete       — Abstract method on LLMProvider; vulture sees the ABC
#                      declaration but not the concrete provider subclasses.
#   bbox             — Dataclass field on Table (ocr/base.py); consumed by
#                      downstream callers that receive Table objects.
#   higher_is_better — RatioResult field; part of the public ratio API contract
#                      (may be surfaced by the UI / future callers).
#   grouped_by_category — Used in tests/test_ratios.py; tests are excluded from
#                      the vulture scan path (paths = ["app", "whitelist.py"]).

updated_at  # unused variable (app/db/models.py:54)
_.complete  # unused method (app/llm/base.py:36)
bbox  # unused variable (app/ocr/base.py:22)
higher_is_better  # unused variable (app/ratios/base.py:59)
grouped_by_category  # unused function (app/ratios/engine.py:49)
models  # unused import (app/db/database.py:32) — side-effect import that registers SQLAlchemy models with DeclarativeBase
