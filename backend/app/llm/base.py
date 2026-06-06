"""Provider-agnostic LLM interface.

The extraction pipeline depends ONLY on this interface, so swapping Anthropic for
OpenAI or a local open-source model (Ollama / vLLM / LM Studio) is a config change,
never a code change. Every provider must support structured (JSON-schema-constrained)
output, because extraction always targets the canonical financial schema.
"""

from __future__ import annotations

import abc
from dataclasses import dataclass
from typing import Any


@dataclass
class LLMResponse:
    """A single LLM completion result and its token accounting."""

    content: str  # raw text (usually JSON)
    parsed: dict[str, Any] | None = None  # parsed JSON when a schema was requested
    model: str = ""
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    raw: Any = None


class LLMProvider(abc.ABC):
    """Base class all providers implement.

    Implementations live in app/llm/providers/: AnthropicProvider, OpenAIProvider,
    OllamaProvider. They are constructed from settings and registered in
    app/llm/factory.py:get_provider(name).
    """

    name: str = "base"

    @abc.abstractmethod
    def complete(
        self,
        *,
        system: str | None,
        prompt: str,
        model: str,
        max_tokens: int = 4096,
        temperature: float = 0.0,
    ) -> LLMResponse:
        """Free-form completion."""

    @abc.abstractmethod
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
        """Completion constrained to return JSON matching ``json_schema``.

        Must populate ``LLMResponse.parsed`` with the decoded object. Providers that
        lack native structured output should fall back to prompt-injected schema +
        robust JSON parsing, and raise ``LLMError`` if the output cannot be parsed.
        """


class LLMError(RuntimeError):
    """Raised when a provider fails to produce a usable response."""
