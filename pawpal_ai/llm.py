"""Thin Groq wrapper that always returns parsed JSON or raises LLMError."""
from __future__ import annotations

import json
import logging
import time
from typing import Protocol

from pawpal_ai.config import groq_api_key, groq_model

log = logging.getLogger("pawpal_ai.llm")


class LLMError(RuntimeError):
    """The model could not be reached or did not return valid JSON."""


class JSONClient(Protocol):
    """Anything that turns chat messages into a JSON dict (Groq, or a fake in tests)."""

    model: str

    def complete_json(self, messages: list[dict], temperature: float = 0.2) -> dict: ...


class GroqJSONClient:
    """Calls a Groq chat model in JSON mode."""

    def __init__(self, model: str | None = None, api_key: str | None = None,
                 timeout: float = 30.0, max_retries: int = 2):
        from groq import Groq  # imported lazily so tests never need the network

        key = api_key or groq_api_key()
        if not key:
            raise LLMError("GROQ_API_KEY is not set. Copy .env.example to .env and add your key.")
        self.model = model or groq_model()
        self._client = Groq(api_key=key, timeout=timeout, max_retries=max_retries)

    def complete_json(self, messages: list[dict], temperature: float = 0.2) -> dict:
        start = time.perf_counter()
        try:
            resp = self._client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=temperature,
                response_format={"type": "json_object"},
            )
        except Exception as exc:  # groq.APIError, timeouts, connection errors
            log.error("Groq call failed (%s): %s", type(exc).__name__, exc)
            raise LLMError(f"Groq request failed: {type(exc).__name__}") from exc

        text = resp.choices[0].message.content or ""
        usage = getattr(resp, "usage", None)
        log.info("Groq %s ok in %.2fs, tokens=%s", self.model, time.perf_counter() - start,
                 getattr(usage, "total_tokens", "?"))
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            log.error("Model returned non-JSON: %.200s", text)
            raise LLMError("Model returned invalid JSON") from exc
        if not isinstance(data, dict):
            raise LLMError("Model returned JSON that is not an object")
        return data
