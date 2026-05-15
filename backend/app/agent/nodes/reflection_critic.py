"""Reflection critic: evaluates the three brief-mandated triggers."""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone

from app.agent.events import emit
from app.agent.state import AgentState
from app.config import get_settings
from app.observability.metrics import reflection_passes as reflection_pass_metric


def trigger_sector_correlation(state: AgentState) -> tuple[bool, str]:
    corr = state.get("tool_results", {}).get("correlation")
    threshold = get_settings().reflection_sector_corr_threshold
    if not corr:
        return False, "correlation tool not run or returned no data"
    sector_corr = corr.get("vs_sector_etf")
    if sector_corr is None:
        return False, "sector ETF correlation unavailable"
    if sector_corr > threshold:
        return True, f"sector ETF correlation {sector_corr:.3f} > {threshold} → idiosyncratic signal missing; need peer comparison"
    return False, f"sector ETF correlation {sector_corr:.3f} ≤ {threshold} (no replan needed)"


def trigger_stale_news(state: AgentState) -> tuple[bool, str]:
    news = state.get("tool_results", {}).get("news_sentiment")
    threshold_hours = get_settings().reflection_stale_news_hours
    if not news:
        return True, "no news fetched"
    articles = news.get("articles") or []
    if not articles:
        return True, "news_sentiment returned zero articles"
    threshold = datetime.now(timezone.utc) - timedelta(hours=threshold_hours)
    pubs = []
    for a in articles:
        p = a.get("published_at")
        if not p:
            continue
        try:
            dt = datetime.fromisoformat(p.replace("Z", "+00:00"))
            pubs.append(dt)
        except Exception:
            continue
    if not pubs:
        return True, "no parseable published_at on any article"
    if all(dt < threshold for dt in pubs):
        return True, f"all {len(pubs)} articles older than {threshold_hours}h → fetch SEC filings"
    return False, f"newest article within {threshold_hours}h window"


def trigger_neutral_sentiment(state: AgentState) -> tuple[bool, str]:
    news = state.get("tool_results", {}).get("news_sentiment")
    if not news:
        return False, "no news data"
    dist = news.get("distribution") or {}
    total = int(dist.get("total", 0))
    if total == 0:
        return False, "empty distribution"
    pos = int(dist.get("positive", 0))
    neg = int(dist.get("negative", 0))
    neu = int(dist.get("neutral", 0))
    perfectly_neutral = pos == 0 and neg == 0 and neu == total
    evenly_split = abs(pos - neg) <= 1 and neu >= math.ceil(total / 2)
    if perfectly_neutral:
        return True, "sentiment is perfectly neutral — needs more context"
    if evenly_split:
        return True, f"evenly split sentiment (pos={pos}, neg={neg}, neu={neu})"
    return False, f"sentiment skews (pos={pos}, neg={neg}, neu={neu})"


async def run(state: AgentState) -> AgentState:
    job_id = state["job_id"]
    settings = get_settings()
    triggers: list[str] = list(state.get("triggers_fired", []))
    thoughts: list[dict] = list(state.get("reflection_thoughts", []))

    fired_now: list[str] = []
    for name, fn in (
        ("sector_correlation", trigger_sector_correlation),
        ("stale_news", trigger_stale_news),
        ("neutral_sentiment", trigger_neutral_sentiment),
    ):
        if name in triggers:
            continue  # already fired in a previous pass
        fired, reasoning = fn(state)
        thoughts.append({"trigger": name, "fired": fired, "reasoning": reasoning})
        await emit(
            job_id,
            "reflection_thought",
            {"trigger_evaluated": name, "fired": fired, "reasoning": reasoning},
        )
        if fired:
            fired_now.append(name)

    new_passes = state.get("reflection_passes", 0) + (1 if fired_now else 0)
    needs_replan = bool(fired_now) and new_passes <= settings.max_reflection_passes

    if needs_replan:
        await emit(job_id, "replan", {"triggers_fired": fired_now, "pass": new_passes})

    reflection_pass_metric.observe(new_passes)

    return {
        **state,
        "triggers_fired": triggers + fired_now,
        "reflection_thoughts": thoughts,
        "needs_replan": needs_replan,
        "reflection_passes": new_passes,
    }
