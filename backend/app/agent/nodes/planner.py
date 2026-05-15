"""Planner node: picks the next tools to call."""

from __future__ import annotations

import json

from app.agent.events import emit
from app.agent.prompts import PLANNER_PROMPT, SYSTEM_PROMPT
from app.agent.state import AgentState
from app.llm.budget import JobBudget
from app.observability.logging import get_logger

log = get_logger(__name__)

ALL_TOOLS = ["market_data", "news_sentiment", "correlation", "peer_fundamentals", "edgar_filings"]
INITIAL_PLAN_TOOLS = ["market_data", "news_sentiment", "correlation"]


async def run(state: AgentState, llm_factory) -> AgentState:
    job_id = state["job_id"]
    triggers = state.get("triggers_fired", [])
    reflection_pass = state.get("reflection_passes", 0)

    if reflection_pass == 0 and not triggers:
        plan_text = "Initial research pass: fetch market data, news+sentiment, and correlations."
        next_tools = INITIAL_PLAN_TOOLS[:]
        await emit(job_id, "planner_decision", {"plan": plan_text, "tools": next_tools, "pass": 0})
        return {**state, "plan": plan_text, "next_tools": next_tools}

    # Reflection-driven plan
    context = {
        "ticker": state.get("ticker"),
        "triggers_fired": triggers,
        "tools_already_used": state.get("tools_used_order", []),
    }
    budget = JobBudget.from_settings()
    llm = llm_factory(budget)
    plan_text = "Reflection pass."
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
        log.warning("planner_llm_failed", error=str(e))

    # Deterministic fallbacks based on triggers
    if "sector_correlation" in triggers and "peer_fundamentals" not in chosen:
        chosen.append("peer_fundamentals")
    if ("stale_news" in triggers or "neutral_sentiment" in triggers) and "edgar_filings" not in chosen:
        chosen.append("edgar_filings")
    if not chosen:
        chosen = ["edgar_filings"]

    await emit(
        job_id,
        "planner_decision",
        {"plan": plan_text, "tools": chosen, "pass": reflection_pass, "triggers": triggers},
    )
    return {**state, "plan": plan_text, "next_tools": chosen}
