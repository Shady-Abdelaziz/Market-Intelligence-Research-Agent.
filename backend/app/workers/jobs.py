"""arq job tasks: run the agent for an analysis job, and the periodic
monitoring tick.
"""

from __future__ import annotations

import asyncio
import contextlib
from datetime import UTC, datetime, timedelta
from typing import Any

from app.agent.events import emit
from app.agent.graph import build_graph, build_tools, llm_factory_default
from app.agent.state import AgentState
from app.cache.dedupe import url_hash
from app.cache.redis_cache import init_cache
from app.config import get_settings
from app.llm.budget import JobBudget
from app.monitoring.baselines import compute_baselines
from app.monitoring.scheduler import is_trading_day
from app.monitoring.triggers import (
    trigger_new_articles,
    trigger_price_2sigma,
    trigger_volume_2x,
)
from app.observability.logging import get_logger, job_id_var
from app.observability.metrics import (
    job_duration_seconds,
    jobs_total,
    monitor_ticks_total,
    monitor_triggers_total,
)
from app.persistence.db import get_session
from app.persistence.repos import JobRepo, LLMCallRepo, MonitorRepo
from app.resilience.http_client import init_client
from app.tools.news_sentiment import NewsSentimentTool

log = get_logger(__name__)


async def _ensure_clients() -> None:
    init_client()
    await init_cache()


# Hard reference set so fire-and-forget tasks aren't GC'd mid-flight in the
# standalone (no-arq) deployment. asyncio only keeps weak references to tasks
# returned by create_task, so without this an idle event loop could collect the
# task and you'd see "Task was destroyed but it is pending" + lost jobs.
_BG_TASKS: set[asyncio.Task[Any]] = set()


async def _run_supervised(job_id: str) -> None:
    """Wrap analyze_ticker for the standalone (no-arq) path.

    analyze_ticker has its own try/except that calls JobRepo.mark_failed and
    emits an `error` event, so under normal failure modes this wrapper is a
    no-op. It only matters when an exception escapes that handler (e.g. the
    DB session itself fails, or BaseException like CancelledError). In that
    case we still want the job row to terminate and the SSE stream to close
    instead of hanging on `queued`.
    """
    try:
        await analyze_ticker({}, job_id)
    except BaseException as e:  # noqa: BLE001
        log.exception("standalone_job_crashed", job_id=job_id)
        with contextlib.suppress(Exception):
            async with get_session() as session:
                job = await JobRepo(session).get(job_id)
                if job and job.status not in ("failed", "completed"):
                    await JobRepo(session).mark_failed(job_id, repr(e))
        with contextlib.suppress(Exception):
            await emit(job_id, "error", {"message": str(e)})
        with contextlib.suppress(Exception):
            await emit(job_id, "done", {"job_id": job_id, "ok": False})
        if isinstance(e, (KeyboardInterrupt, SystemExit)):
            raise


def spawn_inline_job(job_id: str) -> asyncio.Task[None]:
    """Spawn analyze_ticker as a supervised background task and hold a
    strong reference until it finishes. Used only when no arq pool is
    available (standalone deployment / tests)."""
    task = asyncio.create_task(_run_supervised(job_id))
    _BG_TASKS.add(task)
    task.add_done_callback(_BG_TASKS.discard)
    return task


async def analyze_ticker(ctx: dict[str, Any], job_id: str) -> None:
    import time

    token = job_id_var.set(job_id)
    t0 = time.monotonic()
    await _ensure_clients()

    try:
        async with get_session() as session:
            await JobRepo(session).mark_running(job_id)

        # Load job — preserve any pre-set alert/trigger metadata that the
        # monitor_tick has stamped on the row, so the synthesized report can
        # carry PROACTIVE_ALERT and the firing trigger through.
        async with get_session() as session:
            job = await JobRepo(session).get(job_id)
            if not job:
                return
            query = job.query
            alert_tag = job.alert_tag
            preset_triggers: list[str] = list(job.triggers_fired or [])

        # For schema compatibility, monitor_trigger is a single literal —
        # pick the first fired monitor trigger if any.
        monitor_triggers = [
            t for t in preset_triggers if t in ("articles", "price_2sigma", "volume_2x")
        ]
        monitor_trigger = monitor_triggers[0] if monitor_triggers else None

        budget = JobBudget.from_settings()
        tools_by_name = build_tools(llm_factory_default)
        graph = build_graph(llm_factory_default, tools_by_name, budget)

        initial: AgentState = {
            "job_id": str(job_id),
            "query": query,
            "tool_results": {},
            "tools_used_order": [],
            "tool_invocation_logs": [],
            "citation_urls": [],
            "reflection_passes": 0,
            "triggers_fired": [],
            "needs_replan": False,
            "reflection_thoughts": [],
            "errors": [],
            "degraded": False,
            "tokens_used": 0,
            "cost_usd": 0.0,
            "alert_tag": alert_tag,
            "monitor_trigger": monitor_trigger,
        }
        final_state = await graph.ainvoke(initial, {"configurable": {"thread_id": str(job_id)}})

        report = final_state.get("report") or {}
        async with get_session() as session:
            await JobRepo(session).mark_completed(
                job_id=job_id,
                result_json=report,
                prompt_tokens=budget.prompt_tokens,
                completion_tokens=budget.completion_tokens,
                cost_usd=budget.cost_usd,
                tool_calls_count=budget.tool_calls_made,
                reflection_passes=final_state.get("reflection_passes", 0),
                triggers_fired=final_state.get("triggers_fired", []),
                # Preserve PROACTIVE_ALERT (set by monitor_tick before enqueue)
                # or use whatever the state ended up with.
                alert_tag=alert_tag or ctx.get("alert_tag"),
            )
            # Token ledger summary
            for model, slot in budget.per_model.items():
                await LLMCallRepo(session).log(
                    job_id=job_id,
                    model=model,
                    prompt_tokens=int(slot["prompt"]),
                    completion_tokens=int(slot["completion"]),
                    cost_usd=float(slot["cost_usd"]),
                    latency_ms=0,
                )

        jobs_total.labels(status="completed").inc()
        job_duration_seconds.observe(time.monotonic() - t0)
        log.info("job_complete", job_id=job_id)

    except Exception as e:  # noqa: BLE001
        log.error("job_failed", job_id=job_id, error=str(e))
        async with get_session() as session:
            await JobRepo(session).mark_failed(job_id, str(e))
        jobs_total.labels(status="failed").inc()
        with contextlib.suppress(Exception):
            await emit(job_id, "error", {"message": str(e)})
    finally:
        job_id_var.reset(token)


async def _reschedule_monitor_tick(
    ctx: dict[str, Any], target_id: str, cadence_seconds: int
) -> None:
    """Self-enqueue the next monitor tick. arq has no native runtime cron
    API for dynamically-registered jobs, so each tick is responsible for
    scheduling its successor — without this a `monitor_start` would only
    ever fire once."""
    pool = ctx.get("redis")
    if pool is None:
        return
    with contextlib.suppress(Exception):
        await pool.enqueue_job(
            "monitor_tick",
            target_id,
            _queue_name="mira_jobs",
            _defer_by=timedelta(seconds=cadence_seconds),
        )


async def monitor_tick(ctx: dict[str, Any], target_id: str) -> None:
    """Periodic monitoring tick — recompute baselines, evaluate triggers,
    and chain the next tick from the `finally` clause so every exit path
    (non-trading-day, inactive target, baseline failure, happy path)
    keeps the schedule alive."""
    await _ensure_clients()

    # Read target up front so the finally has cadence/active even if the
    # body raises. cadence_seconds defaults to settings if no row exists
    # (in which case we won't reschedule anyway).
    async with get_session() as session:
        target = await MonitorRepo(session).get_by_id(target_id)
        if not target or not target.active:
            monitor_ticks_total.labels(status="target_inactive").inc()
            return  # no reschedule — target deleted/deactivated
        ticker = target.ticker
        cadence_seconds = target.cadence_seconds

    try:
        if not is_trading_day():
            log.info("monitor_skip_non_trading_day", target_id=target_id)
            monitor_ticks_total.labels(status="skipped_non_trading_day").inc()
            return

        # Recompute baselines
        try:
            baselines = await compute_baselines(
                ticker, days=get_settings().monitor_baseline_window_days
            )
        except Exception as e:
            log.warning("monitor_baseline_failed", ticker=ticker, error=str(e))
            monitor_ticks_total.labels(status="failed_baseline_compute").inc()
            return

        # Fetch latest news (just for triggers, we don't classify here)
        tools = build_tools(llm_factory_default)
        news_tool: NewsSentimentTool = tools["news_sentiment"]  # type: ignore
        news_result = await news_tool.invoke(
            budget=JobBudget.from_settings(), ticker=ticker
        )

        article_hashes: list[str] = []
        if news_result.ok and news_result.data:
            for a in news_result.data.get("articles", []):
                if a.get("url"):
                    article_hashes.append(url_hash(a["url"]))

        # Snapshot "new since last seen" BEFORE we re-read the target
        # (the persistence session re-reads to close the merge race).
        prior_seen = set(target.last_seen_article_urls or [])
        new_articles_count = sum(1 for h in article_hashes if h not in prior_seen)

        fired: list[str] = []
        if trigger_new_articles(target, article_hashes):
            fired.append("articles")
            monitor_triggers_total.labels(trigger="articles").inc()
        if trigger_price_2sigma(target, baselines.last_close):
            fired.append("price_2sigma")
            monitor_triggers_total.labels(trigger="price_2sigma").inc()
        if trigger_volume_2x(target, baselines.last_volume):
            fired.append("volume_2x")
            monitor_triggers_total.labels(trigger="volume_2x").inc()

        # Build the fire-time snapshot the UI uses for honest pill labels.
        # All three values come from the baseline ROW the trigger compared
        # against (i.e. the previous tick / monitor_start baseline), not
        # the freshly-recomputed numbers — that's what the trigger actually
        # tripped against.
        snapshot: dict[str, Any] | None = None
        if fired:
            prev_mean = (
                float(target.baseline_price_mean)
                if target.baseline_price_mean is not None
                else None
            )
            prev_std = (
                float(target.baseline_price_std)
                if target.baseline_price_std is not None
                else None
            )
            prev_vol = (
                float(target.baseline_volume_avg)
                if target.baseline_volume_avg is not None
                else None
            )
            snapshot = {
                "new_articles": new_articles_count,
                "price_sigma": (
                    abs(baselines.last_close - prev_mean) / prev_std
                    if prev_mean is not None and prev_std and prev_std > 0
                    else None
                ),
                "volume_ratio": (
                    baselines.last_volume / prev_vol
                    if prev_vol is not None and prev_vol > 0
                    else None
                ),
                "captured_at": datetime.now(UTC).isoformat(),
            }

        # Persist new baselines + article hashes regardless. The repo call
        # below performs the read-merge-write atomically (row lock on
        # Postgres; single-writer serialization on SQLite) so that two
        # concurrent ticks against the same target can't clobber each
        # other's URL history.
        new_job_id: str | None = None
        async with get_session() as session:
            await MonitorRepo(session).merge_seen_urls_and_update_baselines(
                target_id=target.id,
                new_url_hashes=article_hashes,
                baseline_price_mean=baselines.mean,
                baseline_price_std=baselines.std,
                baseline_volume_avg=baselines.volume_avg,
            )

            if fired:
                # Enqueue a new analysis with PROACTIVE_ALERT tag
                job = await JobRepo(session).create(
                    query=(
                        f"Proactive monitoring alert for {ticker} — "
                        f"triggers: {', '.join(fired)}"
                    ),
                    ticker=ticker,
                )
                from sqlalchemy import update

                from app.persistence.models import Job

                await session.execute(
                    update(Job)
                    .where(Job.id == job.id)
                    .values(
                        alert_tag="PROACTIVE_ALERT",
                        monitor_target_id=target.id,
                        triggers_fired=fired,
                        monitor_trigger_snapshot=snapshot,
                    )
                )
                new_job_id = str(job.id)

        if fired and new_job_id:
            pool = ctx.get("redis")
            if pool:
                await pool.enqueue_job(
                    "analyze_ticker", new_job_id, _queue_name="mira_jobs"
                )
            log.info(
                "monitor_alert", ticker=ticker, triggers=fired, new_job_id=new_job_id
            )

        monitor_ticks_total.labels(status="success").inc()
    finally:
        # Re-read the target so a `DELETE /monitor/{ticker}` issued during
        # this tick halts the chain instead of being clobbered by a stale
        # read from the top of the function.
        async with get_session() as session:
            fresh = await MonitorRepo(session).get_by_id(target_id)
            still_active = bool(fresh and fresh.active)
            next_cadence = fresh.cadence_seconds if fresh else cadence_seconds
        if still_active:
            await _reschedule_monitor_tick(ctx, target_id, next_cadence)
