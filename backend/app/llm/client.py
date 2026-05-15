"""LLM client — OpenRouter via the openai SDK.

Implements function calling, streaming, and prompt caching markers. Runs
exclusively against the configured primary model; failures propagate to
the caller, which decides whether to degrade the report.
"""

from __future__ import annotations

import time
from collections.abc import AsyncIterator
from typing import Any

from openai import AsyncOpenAI
from openai.types.chat import ChatCompletion, ChatCompletionChunk

from app.config import get_settings
from app.llm.budget import JobBudget
from app.observability.logging import get_logger
from app.observability.metrics import (
    llm_call_latency_seconds,
    llm_cost_usd_total,
    llm_tokens_total,
)

log = get_logger(__name__)


def _make_client() -> AsyncOpenAI:
    s = get_settings()
    return AsyncOpenAI(
        api_key=s.openrouter_api_key or "missing",
        base_url="https://openrouter.ai/api/v1",
        timeout=s.llm_request_timeout_seconds,
        default_headers={
            "HTTP-Referer": "https://github.com/shady-abdelaziz/market-intelligence-research-agent",
            "X-Title": "M.I.R.A.",
        },
    )


_client: AsyncOpenAI | None = None


def get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        _client = _make_client()
    return _client


class LLMClient:
    """Wrapper that records token usage to a JobBudget and emits metrics."""

    def __init__(self, budget: JobBudget):
        self.budget = budget
        self._client = get_client()
        self._settings = get_settings()

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | dict | None = None,
        model: str | None = None,
        temperature: float | None = None,
        response_format: dict | None = None,
    ) -> ChatCompletion:
        """Non-streaming completion against the primary model."""
        chosen = model or self._settings.llm_primary_model
        t0 = time.monotonic()
        try:
            resp: ChatCompletion = await self._client.chat.completions.create(
                model=chosen,
                messages=self._apply_cache_markers(messages, chosen),
                tools=tools,
                tool_choice=tool_choice,
                temperature=temperature
                if temperature is not None
                else self._settings.llm_temperature,
                max_tokens=self._settings.llm_max_tokens,
                response_format=response_format,
            )
            latency = time.monotonic() - t0
            self._record_usage(resp, chosen, latency)
            return resp
        except Exception as e:  # noqa: BLE001 — openai SDK error variants
            log.warning("llm_call_failed", model=chosen, error=str(e))
            raise

    async def stream(
        self,
        messages: list[dict[str, Any]],
        model: str | None = None,
        temperature: float | None = None,
    ) -> AsyncIterator[ChatCompletionChunk]:
        """Streaming completion against the primary model (no fallback for stream)."""
        chosen = model or self._settings.llm_primary_model
        async for chunk in await self._client.chat.completions.create(
            model=chosen,
            messages=self._apply_cache_markers(messages, chosen),
            temperature=temperature if temperature is not None else self._settings.llm_temperature,
            max_tokens=self._settings.llm_max_tokens,
            stream=True,
            stream_options={"include_usage": True},
        ):
            yield chunk

    def _apply_cache_markers(
        self, messages: list[dict[str, Any]], model: str
    ) -> list[dict[str, Any]]:
        """Mark the system message as cacheable on supported providers."""
        if not self._settings.llm_prompt_cache_enabled:
            return messages
        # OpenRouter passes cache_control through to providers that support it
        out = []
        for m in messages:
            if m.get("role") == "system" and isinstance(m.get("content"), str):
                out.append(
                    {
                        "role": "system",
                        "content": [
                            {
                                "type": "text",
                                "text": m["content"],
                                "cache_control": {"type": "ephemeral"},
                            }
                        ],
                    }
                )
            else:
                out.append(m)
        return out

    def _record_usage(self, resp: ChatCompletion, model: str, latency: float) -> None:
        if not resp.usage:
            return
        pt = resp.usage.prompt_tokens or 0
        ct = resp.usage.completion_tokens or 0
        cost = self.budget.record_llm_usage(model, pt, ct)
        llm_tokens_total.labels(model=model, type="prompt").inc(pt)
        llm_tokens_total.labels(model=model, type="completion").inc(ct)
        llm_cost_usd_total.labels(model=model).inc(cost)
        llm_call_latency_seconds.labels(model=model).observe(latency)
        log.info(
            "llm_call",
            model=model,
            prompt_tokens=pt,
            completion_tokens=ct,
            cost_usd=cost,
            latency_s=latency,
        )
