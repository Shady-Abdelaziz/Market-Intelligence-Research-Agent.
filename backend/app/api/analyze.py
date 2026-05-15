"""POST /analyze — create a job and enqueue it for the worker."""

from __future__ import annotations

from fastapi import APIRouter, Request, status

from app.api.schemas import AnalyzeRequest, AnalyzeResponse
from app.observability.logging import get_logger
from app.persistence.db import get_session
from app.persistence.repos import JobRepo

router = APIRouter(tags=["analyze"])
log = get_logger(__name__)


@router.post("/analyze", response_model=AnalyzeResponse, status_code=status.HTTP_202_ACCEPTED)
async def analyze(req: AnalyzeRequest, request: Request) -> AnalyzeResponse:
    """Submit an analysis. Rate-limited via SlowAPIMiddleware."""
    async with get_session() as session:
        job = await JobRepo(session).create(query=req.query)
        job_id = str(job.id)

    pool = request.app.state.arq_pool
    if pool is not None:
        await pool.enqueue_job("analyze_ticker", job_id, _queue_name="mira_jobs")
    else:
        # Standalone fallback: run inline
        import asyncio
        from app.workers.jobs import analyze_ticker
        asyncio.create_task(analyze_ticker({}, job_id))

    log.info("job_enqueued", job_id=job_id)
    return AnalyzeResponse(job_id=job_id, status="queued")
