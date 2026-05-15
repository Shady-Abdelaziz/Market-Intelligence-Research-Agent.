"""Singleton httpx.AsyncClient managed by FastAPI lifespan.

One HTTP/2-enabled client per process, shared by all tools and the LLM
client. Connection pooling reduces tail latency and memory usage.
"""

from __future__ import annotations

import httpx

_client: httpx.AsyncClient | None = None


def init_client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(
            http2=True,
            timeout=httpx.Timeout(connect=10, read=60, write=30, pool=10),
            limits=httpx.Limits(max_connections=100, max_keepalive_connections=20),
            follow_redirects=True,
        )
    return _client


def get_client() -> httpx.AsyncClient:
    if _client is None:
        return init_client()
    return _client


async def close_client() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None
