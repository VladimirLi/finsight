"""Anthropic provider — wraps the anthropic SDK (Messages API).

Lazy import: the ``anthropic`` package is only imported inside methods so the
application starts even when the SDK is not installed.
"""

from __future__ import annotations

import json
import re
from typing import Any, override

from app.config import get_settings
from app.llm.base import LLMError, LLMProvider, LLMResponse


class AnthropicProvider(LLMProvider):
    """LLM provider backed by Anthropic's Messages API.

    Configure via environment variables:
        ANTHROPIC_API_KEY  — required
        LLM_MODEL          — e.g. "claude-sonnet-4-6" (default from settings)
    """

    name = "anthropic"

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
        """Free-form text completion via the Messages API."""
        client = self._client()

        messages = [{"role": "user", "content": prompt}]
        kwargs: dict[str, Any] = {
            "model": model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": messages,
        }
        if system:
            kwargs["system"] = system

        try:
            response = client.messages.create(**kwargs)
        except Exception as exc:
            raise LLMError(f"Anthropic API error: {exc}") from exc

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

        Strategy: use Anthropic tool-use with ``tool_choice={"type": "tool"}`` so
        the model is *required* to call a single tool whose input schema matches
        ``json_schema``.  The tool input is the parsed JSON object and is placed in
        ``LLMResponse.parsed``.
        """
        client = self._client()

        tool_name = "extract_financials"
        tool = {
            "name": tool_name,
            "description": (
                "Extract structured financial data from the provided text and return "
                "it as a JSON object that strictly matches the supplied schema."
            ),
            "input_schema": json_schema,
        }

        messages = [{"role": "user", "content": prompt}]
        kwargs: dict[str, Any] = {
            "model": model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": messages,
            "tools": [tool],
            "tool_choice": {"type": "tool", "name": tool_name},
        }
        if system:
            kwargs["system"] = system

        try:
            response = client.messages.create(**kwargs)
        except Exception as exc:
            raise LLMError(f"Anthropic API error: {exc}") from exc

        # Extract tool_use block from the response content
        parsed: dict[str, Any] | None = None
        raw_content = ""

        for block in response.content:
            if block.type == "tool_use" and block.name == tool_name:
                parsed = block.input  # already a dict
                raw_content = json.dumps(parsed)
                break
            elif block.type == "text":
                raw_content += block.text

        # Fallback: try to parse JSON from text content if no tool_use block found
        if parsed is None:
            parsed = self._extract_json_from_text(raw_content)

        if parsed is None:
            raise LLMError(
                "Anthropic extract_json: could not obtain a valid JSON object from "
                f"the model response. Raw content: {raw_content[:500]!r}"
            )

        return self._build_response(response, parsed=parsed, content_override=raw_content)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _client(self) -> Any:
        """Lazily import anthropic and build an authenticated client."""
        try:
            import anthropic  # noqa: PLC0415
        except ImportError as exc:
            raise LLMError(
                "The 'anthropic' package is not installed. Run: pip install anthropic"
            ) from exc

        settings = get_settings()
        api_key = settings.anthropic_api_key
        if not api_key:
            raise LLMError(
                "ANTHROPIC_API_KEY is not set. Provide it via the environment or .env file."
            )

        return anthropic.Anthropic(api_key=api_key)

    def _build_response(
        self,
        response: Any,
        *,
        parsed: dict[str, Any] | None,
        content_override: str | None = None,
    ) -> LLMResponse:
        """Convert an Anthropic Message object into an LLMResponse."""
        # Collect text content for the content field
        if content_override is not None:
            content = content_override
        else:
            text_parts = [block.text for block in response.content if hasattr(block, "text")]
            content = "".join(text_parts)

        prompt_tokens: int | None = None
        completion_tokens: int | None = None
        if hasattr(response, "usage") and response.usage is not None:
            prompt_tokens = getattr(response.usage, "input_tokens", None)
            completion_tokens = getattr(response.usage, "output_tokens", None)

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
        """Best-effort JSON extraction from free-form text (fallback path).

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
