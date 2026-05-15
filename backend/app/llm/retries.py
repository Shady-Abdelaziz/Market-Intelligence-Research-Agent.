"""Retry and fallback logic for LLM calls."""

from __future__ import annotations

from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.config import get_settings


def make_llm_retry() -> AsyncRetrying:
    return AsyncRetrying(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type((TimeoutError, ConnectionError)),
        reraise=True,
    )


def get_model_chain() -> list[str]:
    s = get_settings()
    chain = [s.llm_primary_model]
    if s.llm_fallback_model and s.llm_fallback_model != s.llm_primary_model:
        chain.append(s.llm_fallback_model)
    return chain
