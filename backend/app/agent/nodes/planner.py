"""Planner node: picks the next tools to call."""

from __future__ import annotations

import json

from app.agent.events import emit
from app.agent.prompts import PLANNER_PROMPT, SYSTEM_PROMPT
from app.agent.state import AgentState
from app.llm.budget import JobBudget
from app.observability.logging import get_logger

log = get_logger(__name__)

ALL_TOOLS = [
    "market_data",
    "news_sentiment",
    "correlation",
    "peer_fundamentals",
    "edgar_filings",
    "peer_news",
]
INITIAL_PLAN_TOOLS = ["market_data", "news_sentiment", "correlation"]


async def run(state: AgentState, llm_factory) -> AgentState:
    """Ask the LLM what to research next, given the user query (first pass)
    or the results so far + triggers (reflection passes). Falls back to a
    deterministic plan if the LLM is unreachable or returns garbage so the
    agent never blocks on planning."""
    job_id = state["job_id"]
    triggers = state.get("triggers_fired", [])
    reflection_pass = state.get("reflection_passes", 0)
    is_initial = reflection_pass == 0 and not triggers

    context = {
        "phase": "initial" if is_initial else "reflection",
        "query": state.get("query"),
        "ticker": state.get("ticker"),
        "company_name": state.get("company_name"),
        "triggers_fired": triggers,
        "tools_already_used": state.get("tools_used_order", []),
        "tool_results_summary": _summarize_results(state.get("tool_results", {})),
        "available_tools": ALL_TOOLS,
    }
    budget = JobBudget.from_settings()
    llm = llm_factory(budget)

    plan_text = (
        "Initial research pass."
        if is_initial
        else f"Reflection pass — triggers: {', '.join(triggers) or 'unknown'}."
    )
    chosen: list[str] = []
    try:
        resp = await llm.chat(
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": PLANNER_PROMPT + "\n\nContext: " + json.dumps(context)},
            ],
            response_format={"type": "json_object"},
            temperature=0.2,
        )
        parsed = json.loads(resp.choices[0].message.content or "{}")
        plan_text = parsed.get("plan", plan_text)
        for t in parsed.get("tools", []):
            if t in ALL_TOOLS and t not in chosen:
                chosen.append(t)
    except Exception as e:
        log.warning("planner_llm_failed", error=str(e), phase=context["phase"])

    # Fallbacks — keep the agent productive when the LLM is silent or wrong.
    if is_initial and not chosen:
        chosen = INITIAL_PLAN_TOOLS[:]
    if "sector_correlation" in triggers:
        # Trigger 1: brief asks for a competitor's recent news AND price action.
        # Price action lives in the correlation tool's vs_peers; we add peer
        # news here.
        if "peer_news" not in chosen:
            chosen.append("peer_news")
        if "peer_fundamentals" not in chosen:
            chosen.append("peer_fundamentals")
    if (
        "stale_news" in triggers or "neutral_sentiment" in triggers
    ) and "edgar_filings" not in chosen:
        chosen.append("edgar_filings")
    if not chosen:
        chosen = ["edgar_filings"]

    await emit(
        job_id,
        "planner_decision",
        {
            "plan": plan_text,
            "tools": chosen,
            "pass": reflection_pass,
            "triggers": triggers,
            "phase": context["phase"],
        },
    )
    return {**state, "plan": plan_text, "next_tools": chosen}


def _summarize_results(tool_results: dict) -> dict:
    """Compress tool_results into a small dict the LLM can reason over without
    hitting token limits. We surface just the headline shape — counts +
    overall scores — not raw article lists."""
    out: dict = {}
    md = tool_results.get("market_data")
    if md:
        out["market_data"] = {
            "price": md.get("price"),
            "daily_change_pct": md.get("daily_change_pct"),
            "delisted": md.get("delisted"),
        }
    ns = tool_results.get("news_sentiment")
    if ns:
        out["news_sentiment"] = {
            "overall_score": ns.get("overall_score"),
            "confidence": ns.get("confidence"),
            "distribution": ns.get("distribution"),
        }
    corr = tool_results.get("correlation")
    if corr:
        out["correlation"] = {
            "vs_sp500": corr.get("vs_sp500"),
            "vs_sector_etf": corr.get("vs_sector_etf"),
            "sector_etf_symbol": corr.get("sector_etf_symbol"),
            "vs_peers": corr.get("vs_peers"),
        }
    return out
