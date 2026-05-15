"""Monitoring endpoints — start, list, delete, history."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from app.api.schemas import MonitorRecord, MonitorStartRequest
from app.monitoring.baselines import compute_baselines
from app.observability.logging import get_logger
from app.persistence.db import get_session
from app.persistence.repos import MonitorRepo

router = APIRouter(tags=["monitor"])
log = get_logger(__name__)


@router.post("/monitor_start")
async def monitor_start(req: MonitorStartRequest, request: Request) -> dict[str, Any]:
    ticker = req.ticker.upper().strip()
    async with get_session() as session:
        target = await MonitorRepo(session).upsert(
            ticker=ticker,
            cadence_seconds=req.cadence_seconds,
            peers=[p.upper() for p in req.peers],
        )
        # Compute baselines now so the first tick has data to compare against
        try:
            b = await compute_baselines(ticker)
            from sqlalchemy import update
            from app.persistence.models import MonitoringTarget
            await session.execute(
                update(MonitoringTarget)
                .where(MonitoringTarget.id == target.id)
                .values(
                    baseline_price_mean=b.mean,
                    baseline_price_std=b.std,
                    baseline_volume_avg=b.volume_avg,
                    baselines_computed_at=datetime.now(timezone.utc),
                )
            )
        except Exception as e:  # noqa: BLE001
            log.warning("baseline_compute_failed", ticker=ticker, error=str(e))

        target_id = str(target.id)
        cadence = target.cadence_seconds

    # Schedule a cron-like recurring tick on the worker
    pool = request.app.state.arq_pool
    if pool is not None:
        # arq doesn't expose a cron API at runtime; instead enqueue the next
        # tick with a deferred timestamp. The tick re-enqueues itself.
        await pool.enqueue_job(
            "monitor_tick",
            target_id,
            _queue_name="mira_jobs",
            _defer_by=timedelta(seconds=cadence),
        )

    return {
        "id": target_id,
        "ticker": ticker,
        "cadence_seconds": cadence,
        "active": True,
        "next_run_at": (datetime.now(timezone.utc) + timedelta(seconds=cadence)).isoformat(),
    }


@router.get("/monitor", response_model=list[MonitorRecord])
async def list_monitors() -> list[MonitorRecord]:
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
                baseline_price_mean=float(t.baseline_price_mean) if t.baseline_price_mean is not None else None,
                baseline_price_std=float(t.baseline_price_std) if t.baseline_price_std is not None else None,
                baseline_volume_avg=float(t.baseline_volume_avg) if t.baseline_volume_avg is not None else None,
            )
            for t in targets
        ]


@router.delete("/monitor/{ticker}")
async def delete_monitor(ticker: str) -> dict[str, Any]:
    async with get_session() as session:
        deleted = await MonitorRepo(session).deactivate(ticker.upper().strip())
        if not deleted:
            raise HTTPException(status_code=404, detail="not_found")
    return {"ticker": ticker.upper(), "active": False}


@router.get("/monitor/{ticker}/history")
async def monitor_history(ticker: str) -> list[dict[str, Any]]:
    async with get_session() as session:
        rows = await MonitorRepo(session).history(ticker.upper().strip())
        return [
            {
                "job_id": str(r.id),
                "ticker": r.ticker,
                "status": r.status,
                "alert_tag": r.alert_tag,
                "triggers_fired": list(r.triggers_fired or []),
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "completed_at": r.completed_at.isoformat() if r.completed_at else None,
                "report": r.result_json,
            }
            for r in rows
        ]
