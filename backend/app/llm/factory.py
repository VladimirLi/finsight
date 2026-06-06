"""LLM provider factory.

Call ``get_provider(name)`` to obtain the configured ``LLMProvider`` instance.
The ``name`` argument (or ``settings.llm_provider`` when omitted) selects the
implementation; unknown names raise ``LLMError`` rather than failing silently.

Adding a new provider:
1. Create ``app/llm/providers/<name>.py`` with a class that inherits ``LLMProvider``.
2. Register it in ``_REGISTRY`` below.
"""

from __future__ import annotations

from app.config import get_settings
from app.llm.base import LLMError, LLMProvider

# ---------------------------------------------------------------------------
# Registry — maps provider name -> import path + class name.
# Imports are deferred so missing optional SDKs don't break app start-up.
# ---------------------------------------------------------------------------


def _registry() -> dict[str, type[LLMProvider]]:
    """Return a mapping from provider name to provider class.

    Importing here (inside the function) keeps the module-level import list
    minimal while still allowing the factory to be called at any time.
    """
    from app.llm.providers.anthropic import AnthropicProvider  # noqa: PLC0415
    from app.llm.providers.ollama import OllamaProvider  # noqa: PLC0415
    from app.llm.providers.openai import OpenAIProvider  # noqa: PLC0415

    return {
        AnthropicProvider.name: AnthropicProvider,
        OpenAIProvider.name: OpenAIProvider,
        OllamaProvider.name: OllamaProvider,
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def get_provider(name: str | None = None) -> LLMProvider:
    """Return a ready-to-use ``LLMProvider`` instance.

    Parameters
    ----------
    name:
        Provider identifier, e.g. ``"anthropic"``, ``"openai"``, ``"ollama"``.
        When ``None`` (default), ``settings.llm_provider`` is used.

    Raises:
    ------
    LLMError
        If ``name`` is not recognised.
    """
    if name is None:
        settings = get_settings()
        name = settings.llm_provider

    registry = _registry()
    provider_cls = registry.get(name)

    if provider_cls is None:
        available = ", ".join(sorted(registry.keys()))
        raise LLMError(
            f"Unknown LLM provider: {name!r}. "
            f"Available providers: {available}. "
            f"Set LLM_PROVIDER in your .env file to one of these values."
        )

    return provider_cls()
