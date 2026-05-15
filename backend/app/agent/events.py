"""SSE event helpers — pushes events both to the DB (for replay) and to a
per-job in-process pubsub queue (for live streaming).
"""

from __future__ import annotations

import asyncio
import contextlib
import json
from collections import defaultdict
from typing import Any

from app.observability.logging import get_logger
from app.persistence.db import get_session
from app.persistence.repos import EventRepo

log = get_logger(__name__)

# job_id -> list of subscriber queues
_subscribers: dict[str, list[asyncio.Queue[dict[str, Any]]]] = defaultdict(list)


def subscribe(job_id: str) -> asyncio.Queue[dict[str, Any]]:
    q: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=200)
    _subscribers[job_id].append(q)
    return q


def unsubscribe(job_id: str, q: asyncio.Queue) -> None:
    if q in _subscribers.get(job_id, []):
        _subscribers[job_id].remove(q)
    if not _subscribers.get(job_id):
        _subscribers.pop(job_id, None)


async def emit(job_id: str, event_type: str, payload: dict[str, Any]) -> None:
    """Persist + fan-out an agent event."""
    safe = json.loads(json.dumps(payload, default=str))
    try:
        async with get_session() as session:
            await EventRepo(session).append(job_id, event_type, safe)
    except Exception as e:  # noqa: BLE001
        log.warning("event_persist_failed", job_id=job_id, error=str(e))
    for q in list(_subscribers.get(job_id, [])):
        with contextlib.suppress(asyncio.QueueFull):
            q.put_nowait({"event": event_type, "data": safe})
