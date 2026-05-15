"""Tool executor node: runs each tool from state['next_tools'] in order.

Tool inputs are derived from state (ticker, company_name, sector_etf,
peers). Results are merged into state['tool_results'] keyed by tool name.
Each execution logs to tool_invocations and emits tool_start/tool_end SSE.
"""

from __future__ import annotations

from typing import Any

from app.agent.events import emit
from app.agent.state import AgentState
from app.llm.budget import JobBudget
from app.observability.logging import get_logger, job_id_var
from app.persistence.db import get_session
from app.persistence.repos import ToolLogRepo
from app.tools.base import Tool, ToolResult

log = get_logger(__name__)


def _build_args(name: str, state: AgentState) -> dict[str, Any]:
    ticker = state.get("ticker") or ""
    if name == "market_data":
        return {"ticker": ticker}
    if name == "news_sentiment":
        return {"ticker": ticker, "company_name": state.get("company_name")}
    if name == "correlation":
        peers = state.get("peers") or _default_peers(ticker)
        return {
            "ticker": ticker,
            "sector_etf": state.get("sector_etf") or "SPY",
            "peers": peers,
            "window_days": None,
        }
    if name == "peer_fundamentals":
        return {"peers": state.get("peers") or _default_peers(ticker)}
    if name == "edgar_filings":
        return {"ticker": ticker, "days": 30}
    return {"ticker": ticker}


def _default_peers(ticker: str) -> list[str]:
    """Cheap fallback peer list when none provided."""
    common = {
        "AAPL": ["MSFT", "GOOGL"],
        "MSFT": ["GOOGL", "AAPL"],
        "GOOGL": ["MSFT", "META"],
        "TSLA": ["F", "GM"],
        "NVDA": ["AMD", "INTC"],
        "META": ["GOOGL", "SNAP"],
        "AMZN": ["WMT", "GOOGL"],
        "KO": ["PEP", "MNST"],
        "PEP": ["KO", "MDLZ"],
    }
    return common.get(ticker.upper(), [])


async def run(state: AgentState, tools_by_name: dict[str, Tool], budget: JobBudget) -> AgentState:
    job_id = state["job_id"]
    token = job_id_var.set(job_id)

    tool_results = dict(state.get("tool_results", {}))
    tools_used = list(state.get("tools_used_order", []))
    invocation_logs = list(state.get("tool_invocation_logs", []))
    citation_urls = list(state.get("citation_urls", []))
    errors = list(state.get("errors", []))
    degraded = state.get("degraded", False)
    degradation_reason = state.get("degradation_reason")

    try:
        for name in state.get("next_tools", []):
            if name in tools_used and name != "edgar_filings":
                continue  # don't re-run a tool unless explicitly needed by reflection
            tool = tools_by_name.get(name)
            if not tool:
                continue
            args = _build_args(name, state)
            await emit(job_id, "tool_start", {"tool": name, "input": args})

            # news_sentiment's _run() accepts an optional `budget` kwarg used
            # internally for per-article sentiment classification.
            call_kwargs = dict(args)
            if name == "news_sentiment":
                call_kwargs["parent_budget"] = budget
            result: ToolResult = await tool.invoke(budget=budget, **call_kwargs)

            await emit(
                job_id,
                "tool_end",
                {
                    "tool": name,
                    "output_summary": result.summary,
                    "latency_ms": result.latency_ms,
                    "status": result.status,
                    "error": result.error,
                },
            )

            invocation_logs.append(
                {
                    "name": name,
                    "input": {k: v for k, v in args.items() if k != "budget"},
                    "output_summary": result.summary,
                    "latency_ms": result.latency_ms,
                    "status": result.status,
                }
            )
            try:
                async with get_session() as session:
                    await ToolLogRepo(session).log(
                        job_id=job_id,
                        tool_name=name,
                        input_data={k: v for k, v in args.items() if k != "budget"},
                        output_summary=result.summary,
                        latency_ms=result.latency_ms,
                        status=result.status,
                        error=result.error,
                    )
            except Exception as e:  # noqa: BLE001
                log.warning("tool_log_persist_failed", tool=name, error=str(e))

            tools_used.append(name)

            if result.ok and result.data is not None:
                tool_results[name] = result.data
                # If market_data revealed delisted, mark degraded
                if name == "market_data" and result.data.get("delisted"):
                    degraded = True
                    degradation_reason = degradation_reason or "DELISTED"
                # Capture citation URLs from news
                if name == "news_sentiment":
                    for a in result.data.get("articles", []):
                        url = a.get("url")
                        if url and url not in citation_urls:
                            citation_urls.append(url)
            else:
                errors.append(f"{name}:{result.status}:{result.error or ''}")
                if result.status in ("budget_exceeded",):
                    degraded = True
                    degradation_reason = degradation_reason or result.status.upper()

        return {
            **state,
            "tool_results": tool_results,
            "tools_used_order": tools_used,
            "tool_invocation_logs": invocation_logs,
            "tool_calls_made": budget.tool_calls_made,
            "citation_urls": citation_urls,
            "errors": errors,
            "degraded": degraded,
            "degradation_reason": degradation_reason,
            "tokens_used": budget.total_tokens,
            "cost_usd": budget.cost_usd,
        }
    finally:
        job_id_var.reset(token)
