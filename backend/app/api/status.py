"""GET /status/{job_id} and SSE stream."""

from __future__ import annotations

import asyncio
import contextlib
import json
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from sse_starlette.sse import EventSourceResponse

from app.agent.events import subscribe, subscribe_redis, unsubscribe
from app.config import get_settings
from app.persistence.db import get_session
from app.persistence.repos import EventRepo, JobRepo

router = APIRouter(tags=["status"])


@router.get("/status/{job_id}")
async def get_status(job_id: str) -> dict[str, Any]:
    async with get_session() as session:
        job = await JobRepo(session).get(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="job_not_found")
        out: dict[str, Any] = {
            "job_id": str(job.id),
            "query": job.query,
            "status": job.status,
            "created_at": job.created_at.isoformat() if job.created_at else None,
            "started_at": job.started_at.isoformat() if job.started_at else None,
            "completed_at": job.completed_at.isoformat() if job.completed_at else None,
            # Per-job observability per brief §3.C — surface token / cost /
            # budget telemetry that's already persisted on the row.
            "prompt_tokens": job.prompt_tokens,
            "completion_tokens": job.completion_tokens,
            "cost_usd": float(job.cost_usd) if job.cost_usd is not None else None,
            "tool_calls_count": job.tool_calls_count,
            "reflection_passes": job.reflection_passes,
            "alert_tag": job.alert_tag,
        }
        if job.status == "completed" and job.result_json:
            out["report"] = job.result_json
        if job.status == "failed" and job.error:
            out["error"] = job.error
        return out


@router.get("/status/{job_id}/stream")
async def stream_status(job_id: str, request: Request) -> EventSourceResponse:
    async with get_session() as session:
        job = await JobRepo(session).get(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="job_not_found")

    last_event_id_header = request.headers.get("last-event-id")
    last_id = (
        int(last_event_id_header)
        if last_event_id_header and last_event_id_header.isdigit()
        else None
    )

    async def event_gen():
        # Replay backlog
        async with get_session() as session:
            backlog = await EventRepo(session).list_since(job_id, last_id)
            for ev in backlog:
                yield {
                    "id": str(ev.id),
                    "event": ev.event_type,
                    "data": json.dumps(ev.payload, default=str),
                }

        # If job already finished, close out
        async with get_session() as session:
            j = await JobRepo(session).get(job_id)
            if j and j.status in ("completed", "failed"):
                return

        if get_settings().redis_enabled:
            # Cross-process: consume from Redis pub/sub
            agen = subscribe_redis(job_id).__aiter__()
            try:
                while True:
                    if await request.is_disconnected():
                        break
                    try:
                        msg = await asyncio.wait_for(agen.__anext__(), timeout=15.0)
                    except TimeoutError:
                        yield {"event": "ping", "data": "{}"}
                        continue
                    except StopAsyncIteration:
                        break
                    yield {
                        "event": msg["event"],
                        "data": json.dumps(msg["data"], default=str),
                    }
                    if msg["event"] in ("done", "error"):
                        break
            finally:
                with contextlib.suppress(Exception):
                    await agen.aclose()
        else:
            # Single-process fallback
            q = subscribe(job_id)
            try:
                while True:
                    if await request.is_disconnected():
                        break
                    try:
                        msg = await asyncio.wait_for(q.get(), timeout=15.0)
                    except TimeoutError:
                        yield {"event": "ping", "data": "{}"}
                        continue
                    yield {
                        "event": msg["event"],
                        "data": json.dumps(msg["data"], default=str),
                    }
                    if msg["event"] in ("done", "error"):
                        break
            finally:
                unsubscribe(job_id, q)

    return EventSourceResponse(
        event_gen(),
        headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"},
    )
