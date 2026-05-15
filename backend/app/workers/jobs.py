"""arq job tasks: run the agent for an analysis job, and the periodic
monitoring tick.
"""

from __future__ import annotations

import uuid
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


async def analyze_ticker(ctx: dict[str, Any], job_id: str) -> None:
    import time
    token = job_id_var.set(job_id)
    t0 = time.monotonic()
    await _ensure_clients()

    try:
        async with get_session() as session:
            await JobRepo(session).mark_running(job_id)

        # Load job
        async with get_session() as session:
            job = await JobRepo(session).get(job_id)
            if not job:
                return
            query = job.query

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
                alert_tag=ctx.get("alert_tag"),
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
        try:
            await emit(job_id, "error", {"message": str(e)})
        except Exception:
            pass
    finally:
        job_id_var.reset(token)


async def monitor_tick(ctx: dict[str, Any], target_id: str) -> None:
    """Periodic monitoring tick — recompute baselines, evaluate triggers."""
    await _ensure_clients()

    if not is_trading_day():
        log.info("monitor_skip_non_trading_day", target_id=target_id)
        return

    async with get_session() as session:
        target = await MonitorRepo(session).get_by_ticker_id_or_ticker(target_id) if False else None
        # The repo doesn't expose get_by_id, so re-fetch via SQL
        from sqlalchemy import select
        from app.persistence.models import MonitoringTarget
        result = await session.execute(select(MonitoringTarget).where(MonitoringTarget.id == target_id))
        target = result.scalar_one_or_none()
        if not target or not target.active:
            return

        ticker = target.ticker

    # Recompute baselines
    try:
        baselines = await compute_baselines(ticker, days=get_settings().monitor_baseline_window_days)
    except Exception as e:
        log.warning("monitor_baseline_failed", ticker=ticker, error=str(e))
        return

    # Fetch latest news (just for triggers, we don't classify here)
    tools = build_tools(llm_factory_default)
    news_tool: NewsSentimentTool = tools["news_sentiment"]  # type: ignore
    news_result = await news_tool.invoke(budget=JobBudget.from_settings(), ticker=ticker)

    article_hashes: list[str] = []
    if news_result.ok and news_result.data:
        for a in news_result.data.get("articles", []):
            if a.get("url"):
                article_hashes.append(url_hash(a["url"]))

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

    # Persist new baselines + article hashes regardless
    async with get_session() as session:
        merged_urls = list(dict.fromkeys((target.last_seen_article_urls or []) + article_hashes))[-50:]
        await MonitorRepo(session).update_baselines_and_run(
            target_id=target.id,
            baseline_price_mean=baselines.mean,
            baseline_price_std=baselines.std,
            baseline_volume_avg=baselines.volume_avg,
            last_seen_article_urls=merged_urls,
        )

        if fired:
            # Enqueue a new analysis with PROACTIVE_ALERT tag
            job = await JobRepo(session).create(
                query=f"Proactive monitoring alert for {ticker} — triggers: {', '.join(fired)}",
                ticker=ticker,
            )
            # Tag job + link to target
            from sqlalchemy import update
            from app.persistence.models import Job
            await session.execute(
                update(Job).where(Job.id == job.id).values(
                    alert_tag="PROACTIVE_ALERT",
                    monitor_target_id=target.id,
                    triggers_fired=fired,
                )
            )
            new_job_id = str(job.id)

    if fired:
        # Enqueue the analysis on the worker (self-enqueue via redis_pool)
        pool = ctx.get("redis")
        if pool:
            await pool.enqueue_job("analyze_ticker", new_job_id, _queue_name="mira_jobs")
        log.info("monitor_alert", ticker=ticker, triggers=fired, new_job_id=new_job_id)


# Patch MonitorRepo dummy method used above
def _patch_repo() -> None:
    from app.persistence import repos as _repos
    if not hasattr(_repos.MonitorRepo, "get_by_ticker_id_or_ticker"):
        async def _stub(self, _):
            return None
        _repos.MonitorRepo.get_by_ticker_id_or_ticker = _stub  # type: ignore


_patch_repo()
