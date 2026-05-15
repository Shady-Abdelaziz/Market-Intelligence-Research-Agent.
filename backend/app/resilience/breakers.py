"""Circuit breakers per upstream API.

Separate from retry/backoff: when an upstream is failing repeatedly, the
breaker opens and short-circuits subsequent calls until the cooldown
elapses. Each upstream gets its own breaker instance.
"""

from __future__ import annotations

import contextlib
from typing import Any

import pybreaker

from app.config import get_settings
from app.observability.metrics import circuit_breaker_state

_settings = get_settings()


class _MetricListener(pybreaker.CircuitBreakerListener):
    def __init__(self, upstream: str):
        self.upstream = upstream

    def state_change(self, _cb: pybreaker.CircuitBreaker, old, new) -> None:
        mapping = {"closed": 0, "open": 1, "half-open": 2}
        circuit_breaker_state.labels(upstream=self.upstream).set(
            mapping.get(getattr(new, "name", str(new)).lower(), 0)
        )


def _make_breaker(upstream: str) -> pybreaker.CircuitBreaker:
    return pybreaker.CircuitBreaker(
        fail_max=_settings.breaker_fail_max,
        reset_timeout=_settings.breaker_reset_timeout_seconds,
        name=upstream,
        listeners=[_MetricListener(upstream)],
    )


breakers: dict[str, pybreaker.CircuitBreaker] = {
    "yfinance": _make_breaker("yfinance"),
    "newsapi": _make_breaker("newsapi"),
    "marketaux": _make_breaker("marketaux"),
    "edgar": _make_breaker("edgar"),
    "openrouter": _make_breaker("openrouter"),
}


class CircuitOpenError(RuntimeError):
    pass


def call_breaker(upstream: str, fn, /, *args, **kwargs) -> Any:
    """Synchronous helper (yfinance is sync). For async use call_breaker_async."""
    breaker = breakers[upstream]
    try:
        return breaker.call(fn, *args, **kwargs)
    except pybreaker.CircuitBreakerError as e:
        raise CircuitOpenError(f"Circuit open for {upstream}") from e


async def call_breaker_async(upstream: str, coro_fn, /, *args, **kwargs) -> Any:
    """Async-aware breaker wrapper.

    pybreaker doesn't natively support coroutines so we replicate the
    failure-counting logic on top of the underlying breaker primitives.
    """
    breaker = breakers[upstream]
    if breaker.current_state == "open":
        raise CircuitOpenError(f"Circuit open for {upstream}")
    try:
        result = await coro_fn(*args, **kwargs)
    except Exception:
        # Manually record failure on the breaker
        with contextlib.suppress(Exception):
            breaker.call(lambda: (_ for _ in ()).throw(Exception("recorded failure")))
        raise
    # Success — reset the breaker if it was half-open
    with contextlib.suppress(Exception):
        breaker.call(lambda: None)
    return result
