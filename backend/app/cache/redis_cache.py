"""Async TTL cache backed by Redis.

When REDIS_URL is unset (standalone mode), falls back to a process-local
in-memory dict with TTL semantics. All cache operations are no-ops on miss
and JSON-serialize on store, so values must be JSON-safe.
"""

from __future__ import annotations

import json
import time
from typing import Any

import redis.asyncio as aioredis

from app.config import get_settings
from app.observability.metrics import cache_hits_total, cache_misses_total

_redis: aioredis.Redis | None = None
_inmem: dict[str, tuple[float, str]] = {}


async def init_cache() -> None:
    global _redis
    settings = get_settings()
    if settings.redis_enabled and _redis is None:
        _redis = aioredis.from_url(settings.redis_url, decode_responses=True)


async def close_cache() -> None:
    global _redis
    if _redis is not None:
        await _redis.aclose()
        _redis = None


async def get(cache_name: str, key: str) -> Any | None:
    full_key = f"mira:{cache_name}:{key}"
    if _redis is not None:
        raw = await _redis.get(full_key)
    else:
        entry = _inmem.get(full_key)
        if entry is None:
            cache_misses_total.labels(cache=cache_name).inc()
            return None
        expires_at, value = entry
        if expires_at < time.time():
            _inmem.pop(full_key, None)
            cache_misses_total.labels(cache=cache_name).inc()
            return None
        raw = value
    if raw is None:
        cache_misses_total.labels(cache=cache_name).inc()
        return None
    cache_hits_total.labels(cache=cache_name).inc()
    return json.loads(raw)


async def set(cache_name: str, key: str, value: Any, ttl_seconds: int) -> None:
    full_key = f"mira:{cache_name}:{key}"
    payload = json.dumps(value, default=str)
    if _redis is not None:
        await _redis.set(full_key, payload, ex=ttl_seconds)
    else:
        _inmem[full_key] = (time.time() + ttl_seconds, payload)
