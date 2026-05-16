"""Monitoring endpoints — start, list, delete, history."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from app.api.schemas import MonitorRecord, MonitorStartRequest
from app.config import get_settings
from app.monitoring.baselines import compute_baselines
from app.observability.logging import get_logger
from app.observability.ratelimit import limiter
from app.persistence.db import get_session
from app.persistence.repos import JobRepo, MonitorRepo

router = APIRouter(tags=["monitor"])
log = get_logger(__name__)
_settings = get_settings()


@router.post("/monitor_start")
@limiter.limit(_settings.ratelimit_monitor)
async def monitor_start(request: Request, req: MonitorStartRequest) -> dict[str, Any]:
    ticker = req.ticker.upper().strip()

    # Compute baselines FIRST. If the ticker is delisted, has no history,
    # or yfinance is rate-limited, we refuse the registration with 400 —
    # the alternative (creating a row with no baselines) leaves a
    # permanently-broken monitor in the UI that can never fire.
    try:
        b = await compute_baselines(ticker)
    except Exception as e:  # noqa: BLE001
        log.warning("monitor_start_baseline_failed", ticker=ticker, error=str(e))
        raise HTTPException(
            status_code=400,
            detail={
                "code": "BASELINE_COMPUTE_FAILED",
                "ticker": ticker,
                "reason": str(e),
            },
        ) from e

    async with get_session() as session:
        target = await MonitorRepo(session).upsert(
            ticker=ticker,
            cadence_seconds=req.cadence_seconds,
            peers=[p.upper() for p in req.peers],
        )

        from sqlalchemy import update

        from app.persistence.models import MonitoringTarget

        await session.execute(
            update(MonitoringTarget)
            .where(MonitoringTarget.id == target.id)
            .values(
                baseline_price_mean=b.mean,
                baseline_price_std=b.std,
                baseline_volume_avg=b.volume_avg,
                baselines_computed_at=datetime.now(UTC),
            )
        )

        target_id = str(target.id)
        cadence = target.cadence_seconds

        # Create a baseline analysis job tied to this monitor so the UI
        # row has content from second zero instead of waiting for the
        # first scheduled tick (1h+ later). alert_tag stays None — this
        # is a normal report, not a PROACTIVE_ALERT.
        from sqlalchemy import update

        from app.persistence.models import Job

        baseline_job = await JobRepo(session).create(
            query=f"Baseline analysis for {ticker} (monitor cold-start)",
            ticker=ticker,
        )
        await session.execute(
            update(Job)
            .where(Job.id == baseline_job.id)
            .values(monitor_target_id=target.id)
        )
        initial_job_id = str(baseline_job.id)

    # Schedule the first tick on the worker. Each tick self-enqueues the
    # next one (see workers.jobs._reschedule_monitor_tick), so this is the
    # only place we kick off the chain.
    pool = request.app.state.arq_pool
    if pool is not None:
        # Baseline analysis runs immediately so the monitor row populates.
        await pool.enqueue_job(
            "analyze_ticker", initial_job_id, _queue_name="mira_jobs"
        )
        # Scheduled monitoring tick chain.
        await pool.enqueue_job(
            "monitor_tick",
            target_id,
            _queue_name="mira_jobs",
            _defer_by=timedelta(seconds=cadence),
        )
    else:
        # Standalone fallback — mirror analyze.py's behaviour so single-
        # container deploys still produce a baseline report. Supervised so
        # a worker crash still terminates the job row + SSE stream.
        from app.workers.jobs import spawn_inline_job

        spawn_inline_job(initial_job_id)

    return {
        "id": target_id,
        "ticker": ticker,
        "cadence_seconds": cadence,
        "active": True,
        "initial_job_id": initial_job_id,
        "next_run_at": (datetime.now(UTC) + timedelta(seconds=cadence)).isoformat(),
    }


@router.get("/monitor", response_model=list[MonitorRecord])
@limiter.limit(_settings.ratelimit_monitor)
async def list_monitors(request: Request) -> list[MonitorRecord]:
    async with get_session() as session:
        targets = await MonitorRepo(session).list_active()
        return [
            MonitorRecord(
                id=str(t.id),
                ticker=t.ticker,
                cadence_seconds=t.cadence_seconds,
                peers=list(t.peers or []),
                active=t.active,
                last_run_at=t.last_run_at,
                baseline_price_mean=float(t.baseline_price_mean)
                if t.baseline_price_mean is not None
                else None,
                baseline_price_std=float(t.baseline_price_std)
                if t.baseline_price_std is not None
                else None,
                baseline_volume_avg=float(t.baseline_volume_avg)
                if t.baseline_volume_avg is not None
                else None,
            )
            for t in targets
        ]


@router.delete("/monitor/{ticker}")
@limiter.limit(_settings.ratelimit_monitor)
async def delete_monitor(request: Request, ticker: str) -> dict[str, Any]:
    """Idempotent — a 404 on a missing/already-deactivated monitor used to
    surface as a UI error on double-click. Return 200 either way and let
    the caller see whether something was actually deactivated via
    `was_active`."""
    async with get_session() as session:
        was_active = await MonitorRepo(session).deactivate(ticker.upper().strip())
    return {"ticker": ticker.upper(), "active": False, "was_active": was_active}


@router.get("/monitor/{ticker}/history")
@limiter.limit(_settings.ratelimit_monitor)
async def monitor_history(request: Request, ticker: str) -> list[dict[str, Any]]:
    async with get_session() as session:
        rows = await MonitorRepo(session).history(ticker.upper().strip())
        return [
            {
                "job_id": str(r.id),
                "ticker": r.ticker,
                "status": r.status,
                "alert_tag": r.alert_tag,
                "triggers_fired": list(r.triggers_fired or []),
                "monitor_trigger_snapshot": r.monitor_trigger_snapshot,
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "completed_at": r.completed_at.isoformat() if r.completed_at else None,
                "report": r.result_json,
            }
            for r in rows
        ]
