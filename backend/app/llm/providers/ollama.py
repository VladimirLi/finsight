"""Ollama provider — drives a local Ollama server via its REST API.

Uses ``httpx`` for HTTP (lazy import) rather than any Ollama-specific SDK so
the dependency surface is minimal. Targets the ``/api/chat`` endpoint.

Lazy import: ``httpx`` is only imported inside methods.
"""

from __future__ import annotations

import json
import re
from typing import Any, override

from app.config import get_settings
from app.llm.base import LLMError, LLMProvider, LLMResponse


class OllamaProvider(LLMProvider):
    """LLM provider backed by a locally-running Ollama server.

    Configure via environment variables:
        OLLAMA_BASE_URL — default "http://localhost:11434"
        LLM_MODEL       — e.g. "llama3.1:70b" (default from settings)
    """

    name = "ollama"

    # Ollama API timeout (seconds). Increase for very large models / slow hardware.
    _TIMEOUT = 300.0

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
        """Free-form text completion via Ollama /api/chat."""
        payload = self._build_payload(
            system=system,
            prompt=prompt,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            response_format=None,
        )
        data = self._post(payload)
        if data is None:
            raise LLMError("Ollama complete: received no response data.")
        return self._build_response(data, parsed=None, model=model)

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
        """Structured JSON completion.

        Ollama supports two ways to constrain output to JSON:
        - Older: ``"format": "json"``  — instructs the model to reply with JSON.
        - Newer (≥ 0.3): ``"format": <json-schema-object>`` — schema-constrained.

        We first attempt the schema-constrained form; if the server rejects it
        (HTTP 4xx or non-JSON response), we fall back to ``"format": "json"`` +
        robust text parsing.

        The schema hint is also injected into the prompt for models that benefit
        from it.
        """
        schema_hint = json.dumps(json_schema, indent=2)
        augmented_prompt = (
            f"{prompt}\n\n"
            f"Respond with a valid JSON object that strictly matches this schema:\n"
            f"```json\n{schema_hint}\n```\n"
            f"Return ONLY the JSON object — no prose, no code fences."
        )

        # Attempt 1: pass the schema object as ``format`` (Ollama ≥ 0.3)
        payload = self._build_payload(
            system=system,
            prompt=augmented_prompt,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            response_format=json_schema,
        )
        data = self._post(payload, raise_on_http_error=False)

        if data is not None:
            content = self._message_content(data)
            parsed = self._extract_json_from_text(content)
            if parsed is not None:
                return self._build_response(data, parsed=parsed, model=model)

        # Attempt 2: ``format: "json"`` fallback
        payload_fallback = self._build_payload(
            system=system,
            prompt=augmented_prompt,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            response_format="json",
        )
        data_fallback = self._post(payload_fallback)
        if data_fallback is None:
            raise LLMError("Ollama extract_json: fallback request returned no response data.")
        content = self._message_content(data_fallback)
        parsed = self._extract_json_from_text(content)

        if parsed is None:
            raise LLMError(
                "Ollama extract_json: could not parse a JSON object from the model "
                f"response. Raw content: {content[:500]!r}"
            )

        return self._build_response(data_fallback, parsed=parsed, model=model)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _post(
        self,
        payload: dict[str, Any],
        *,
        raise_on_http_error: bool = True,
    ) -> dict[str, Any] | None:
        """POST to /api/chat and return the parsed JSON response.

        If ``raise_on_http_error`` is False, returns None on HTTP error instead
        of raising so callers can fall back gracefully.
        """
        try:
            import httpx  # noqa: PLC0415
        except ImportError as exc:
            raise LLMError("The 'httpx' package is not installed. Run: pip install httpx") from exc

        settings = get_settings()
        base_url = settings.ollama_base_url.rstrip("/")
        url = f"{base_url}/api/chat"

        try:
            response = httpx.post(
                url,
                json=payload,
                timeout=self._TIMEOUT,
            )
        except httpx.RequestError as exc:
            raise LLMError(
                f"Ollama request failed (is Ollama running at {base_url}?): {exc}"
            ) from exc

        if not response.is_success:
            if not raise_on_http_error:
                return None
            raise LLMError(f"Ollama returned HTTP {response.status_code}: {response.text[:300]}")

        try:
            result: dict[str, Any] = response.json()
            return result
        except Exception as exc:
            if not raise_on_http_error:
                return None
            raise LLMError(f"Ollama response is not valid JSON: {response.text[:300]}") from exc

    @staticmethod
    def _build_payload(
        *,
        system: str | None,
        prompt: str,
        model: str,
        temperature: float,
        max_tokens: int,
        response_format: Any,  # None | "json" | dict (schema)
    ) -> dict[str, Any]:
        """Build the /api/chat request body."""
        messages: list[dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            },
        }

        if response_format is not None:
            payload["format"] = response_format

        return payload

    @staticmethod
    def _message_content(data: dict[str, Any]) -> str:
        """Extract the assistant message content from /api/chat response."""
        try:
            content: str = data["message"]["content"]
            return content
        except (KeyError, TypeError):
            return ""

    @staticmethod
    def _build_response(
        data: dict[str, Any],
        *,
        parsed: dict[str, Any] | None,
        model: str,
    ) -> LLMResponse:
        """Convert an Ollama /api/chat response dict into an LLMResponse."""
        content = OllamaProvider._message_content(data)

        # Ollama reports token counts in the top-level response object
        prompt_tokens: int | None = data.get("prompt_eval_count")
        completion_tokens: int | None = data.get("eval_count")

        actual_model: str = data.get("model", model)

        return LLMResponse(
            content=content,
            parsed=parsed,
            model=actual_model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            raw=data,
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
