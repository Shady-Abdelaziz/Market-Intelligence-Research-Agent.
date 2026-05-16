"""Regression test: SSE in-process fanout no longer silently drops events
when a subscriber is slow — it pushes a `lagged` sentinel so the SSE
handler can re-replay from the durable event log."""

from __future__ import annotations

import asyncio

import pytest

from app.agent import events as events_mod


@pytest.mark.asyncio
async def test_full_subscriber_gets_lagged_sentinel(monkeypatch):
    # Prevent the emit() call from touching the DB / Redis — we only want
    # to exercise the in-process fanout branch.
    async def _noop_persist(*args, **kwargs):
        return None

    async def _no_redis():
        return None

    monkeypatch.setattr(events_mod, "_get_pub", _no_redis)

    # Bypass DB persistence path inside emit by monkeypatching the
    # EventRepo.append used inside the get_session() block.
    from app.persistence import repos as repos_mod

    async def _fake_append(self, job_id, event_type, payload):  # noqa: ARG001
        return None

    monkeypatch.setattr(repos_mod.EventRepo, "append", _fake_append)

    # Also stub get_session so we don't need a real engine.
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def _fake_session():
        yield None

    monkeypatch.setattr(events_mod, "get_session", _fake_session)

    job_id = "job-x"
    # Manually install a tiny queue so we can force QueueFull on the next put.
    q: asyncio.Queue = asyncio.Queue(maxsize=1)
    events_mod._subscribers[job_id].append(q)
    try:
        await events_mod.emit(job_id, "tool_start", {"tool": "market_data"})
        # Queue is now full. The next emit must NOT silently drop —
        # it should drain the old event and push a `lagged` sentinel.
        await events_mod.emit(job_id, "token", {"text": "hello"})
        items: list[dict] = []
        while not q.empty():
            items.append(q.get_nowait())
        kinds = [m["event"] for m in items]
        assert "lagged" in kinds
    finally:
        events_mod._subscribers.pop(job_id, None)
