"""OpenAI provider — wraps the openai SDK.

Supports the standard OpenAI API and any OpenAI-compatible endpoint (vLLM,
LM Studio, Azure, etc.) via ``settings.openai_base_url``.

Lazy import: the ``openai`` package is only imported inside methods so the
application starts even when the SDK is not installed.
"""

from __future__ import annotations

import json
import re
from typing import Any, override

from app.config import get_settings
from app.llm.base import LLMError, LLMProvider, LLMResponse


class OpenAIProvider(LLMProvider):
    """LLM provider backed by the OpenAI Chat Completions API.

    Configure via environment variables:
        OPENAI_API_KEY      — required for the real OpenAI endpoint
        OPENAI_BASE_URL     — optional; point to a local/compatible server
        LLM_MODEL           — e.g. "gpt-4o" (default from settings)
    """

    name = "openai"

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

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
        """Free-form text completion via the Chat Completions API."""
        client = self._client()
        messages = self._build_messages(system=system, prompt=prompt)

        try:
            response = client.chat.completions.create(
                model=model,
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature,
            )
        except Exception as exc:
            raise LLMError(f"OpenAI API error: {exc}") from exc

        return self._build_response(response, parsed=None)

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
        """Structured completion constrained to ``json_schema``.

        Strategy (in order of preference):
        1. ``response_format`` with ``json_schema`` type (supported by gpt-4o and
           later models; also by many compatible servers).
        2. ``response_format={"type": "json_object"}`` (older fallback) + robust
           JSON parsing from the reply text.

        ``LLMResponse.parsed`` is always populated on success.
        """
        client = self._client()
        messages = self._build_messages(system=system, prompt=prompt)

        # Augment system prompt to hint JSON output (helps both strategies)
        schema_hint = json.dumps(json_schema, indent=2)
        json_guidance = (
            f"\n\nYou MUST respond with a valid JSON object that strictly matches "
            f"the following JSON Schema:\n```json\n{schema_hint}\n```\n"
            f"Return ONLY the JSON object — no prose, no code fences."
        )
        # Inject guidance into the last user message
        augmented_messages = list(messages)
        if augmented_messages and augmented_messages[-1]["role"] == "user":
            augmented_messages[-1] = {
                "role": "user",
                "content": augmented_messages[-1]["content"] + json_guidance,
            }

        # Attempt 1: structured output with json_schema response_format
        response = self._try_json_schema_format(
            client=client,
            messages=augmented_messages,
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            json_schema=json_schema,
        )
        if response is not None:
            return response

        # Attempt 2: json_object response_format (best-effort parse)
        response = self._try_json_object_format(
            client=client,
            messages=augmented_messages,
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        if response is not None:
            return response

        # Attempt 3: plain completion + robust parse
        try:
            raw_response = client.chat.completions.create(
                model=model,
                messages=augmented_messages,
                max_tokens=max_tokens,
                temperature=temperature,
            )
        except Exception as exc:
            raise LLMError(f"OpenAI API error: {exc}") from exc

        content = raw_response.choices[0].message.content or ""
        parsed = self._extract_json_from_text(content)
        if parsed is None:
            raise LLMError(
                "OpenAI extract_json: could not parse a JSON object from the model "
                f"response. Raw content: {content[:500]!r}"
            )
        return self._build_response(raw_response, parsed=parsed)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _client(self) -> Any:
        """Lazily import openai and build an authenticated client."""
        try:
            import openai  # noqa: PLC0415
        except ImportError as exc:
            raise LLMError(
                "The 'openai' package is not installed. Run: pip install openai"
            ) from exc

        settings = get_settings()
        kwargs: dict[str, Any] = {}
        if settings.openai_api_key:
            kwargs["api_key"] = settings.openai_api_key
        if settings.openai_base_url:
            kwargs["base_url"] = settings.openai_base_url

        return openai.OpenAI(**kwargs)

    @staticmethod
    def _build_messages(system: str | None, prompt: str) -> list[dict[str, str]]:
        messages: list[dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        return messages

    def _try_json_schema_format(
        self,
        *,
        client: Any,
        messages: list[dict[str, str]],
        model: str,
        max_tokens: int,
        temperature: float,
        json_schema: dict[str, Any],
    ) -> LLMResponse | None:
        """Try the strict ``json_schema`` response_format (OpenAI ≥ gpt-4o-2024-08-06)."""
        schema_name = json_schema.get("title", "extraction_result")
        # Sanitize schema name to alphanumeric + underscores
        schema_name = re.sub(r"[^a-zA-Z0-9_-]", "_", str(schema_name))

        try:
            response = client.chat.completions.create(
                model=model,
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature,
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": schema_name,
                        "schema": json_schema,
                        "strict": True,
                    },
                },
            )
        except Exception:
            # Model or server may not support json_schema response_format
            return None

        content = response.choices[0].message.content or ""
        parsed = self._extract_json_from_text(content)
        if parsed is None:
            return None
        return self._build_response(response, parsed=parsed)

    def _try_json_object_format(
        self,
        *,
        client: Any,
        messages: list[dict[str, str]],
        model: str,
        max_tokens: int,
        temperature: float,
    ) -> LLMResponse | None:
        """Try the ``json_object`` response_format (older / wider compatibility)."""
        try:
            response = client.chat.completions.create(
                model=model,
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature,
                response_format={"type": "json_object"},
            )
        except Exception:
            return None

        content = response.choices[0].message.content or ""
        parsed = self._extract_json_from_text(content)
        if parsed is None:
            return None
        return self._build_response(response, parsed=parsed)

    @staticmethod
    def _build_response(response: Any, *, parsed: dict[str, Any] | None) -> LLMResponse:
        """Convert a ChatCompletion object into an LLMResponse."""
        choice = response.choices[0]
        content = choice.message.content or ""

        prompt_tokens: int | None = None
        completion_tokens: int | None = None
        if hasattr(response, "usage") and response.usage is not None:
            prompt_tokens = getattr(response.usage, "prompt_tokens", None)
            completion_tokens = getattr(response.usage, "completion_tokens", None)

        return LLMResponse(
            content=content,
            parsed=parsed,
            model=response.model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            raw=response,
        )

    @staticmethod
    def _extract_json_from_text(text: str) -> dict[str, Any] | None:
        """Best-effort JSON extraction from free-form text.

        Tries, in order:
        1. Parse the whole string as JSON.
        2. Extract the first ```json ... ``` code fence.
        3. Find the first ``{`` and match its closing ``}``.
        """
        text = text.strip()
        if not text:
            return None

        # Attempt 1: whole string
        try:
            parsed: Any = json.loads(text)
            if isinstance(parsed, dict):
                result: dict[str, Any] = parsed
                return result
        except (json.JSONDecodeError, ValueError):
            pass

        # Attempt 2: code fence
        fence_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
        if fence_match:
            try:
                parsed = json.loads(fence_match.group(1))
                if isinstance(parsed, dict):
                    result = parsed
                    return result
            except (json.JSONDecodeError, ValueError):
                pass

        # Attempt 3: first balanced brace
        start = text.find("{")
        if start != -1:
            depth = 0
            for i, ch in enumerate(text[start:], start):
                if ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0:
                        try:
                            parsed = json.loads(text[start : i + 1])
                            if isinstance(parsed, dict):
                                result = parsed
                                return result
                        except (json.JSONDecodeError, ValueError):
                            pass
                        break

        return None
