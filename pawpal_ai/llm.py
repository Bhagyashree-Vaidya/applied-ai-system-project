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

    GENERATION_ATTEMPTS = 3
    RETRYABLE = ("output_parse_failed", "tool_use_failed")

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
        resp = self._create(model=self.model, messages=messages, temperature=temperature,
                            response_format={"type": "json_object"})
        return self._parse_json(resp, start)

    def call_tool(self, messages: list[dict], tools: list[dict], temperature: float = 0.2) -> dict:
        """Ask the model for its next tool call (native Groq tool calling).

        Returns {"id", "action", "args", "thought"}. A plain-text reply with no tool call means the
        model considers the job done, so it is returned as action "finish" with the text as thought.
        """
        start = time.perf_counter()
        resp = self._create(model=self.model, messages=messages, tools=tools, tool_choice="auto",
                            temperature=temperature)
        msg = resp.choices[0].message
        if not msg.tool_calls:
            text = " ".join((msg.content or "").split())
            log.info("Groq %s replied without a tool call; treating as finish", self.model)
            return {"id": None, "action": "finish", "args": {}, "thought": text[:300]}
        call = msg.tool_calls[0]
        try:
            args = json.loads(call.function.arguments or "{}")
        except json.JSONDecodeError:
            args = {"_invalid_json": call.function.arguments}
        thought = (msg.content or getattr(msg, "reasoning", None) or "").strip()
        log.info("Groq %s tool=%s in %.2fs", self.model, call.function.name, time.perf_counter() - start)
        return {"id": call.id, "action": call.function.name, "args": args if isinstance(args, dict) else {},
                "thought": " ".join(thought.split())[:300]}

    def _create(self, **kwargs):
        """chat.completions.create with retries for Groq's malformed-generation 400s."""
        for attempt in range(1, self.GENERATION_ATTEMPTS + 1):
            try:
                return self._client.chat.completions.create(**kwargs)
            except Exception as exc:  # groq.APIError, timeouts, connection errors
                # Groq returns HTTP 400 "output_parse_failed" / "tool_use_failed" when a sampled generation
                # is not valid JSON or names a tool badly; that is a sampling hiccup, so sample again.
                if any(c in str(exc) for c in self.RETRYABLE) and attempt < self.GENERATION_ATTEMPTS:
                    log.warning("Groq malformed generation (attempt %d): %.160s; retrying", attempt, exc)
                    continue
                log.error("Groq call failed (%s): %s", type(exc).__name__, exc)
                raise LLMError(f"Groq request failed: {type(exc).__name__}") from exc

    def _parse_json(self, resp, start: float) -> dict:
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
