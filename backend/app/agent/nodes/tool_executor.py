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
    if name == "peer_news":
        return {
            "peers": state.get("peers") or _default_peers(ticker),
            "company_name": state.get("company_name"),
        }
    if name == "edgar_filings":
        return {"ticker": ticker, "days": 30}
    return {"ticker": ticker}


def _trim_for_stream(name: str, data: Any) -> Any:
    """Trim a tool's structured result for the SSE wire — keep the fields the
    live UI needs, drop heavy payloads."""
    if not isinstance(data, dict):
        return data
    if name in ("news_sentiment", "peer_news"):
        return {
            "ticker": data.get("ticker"),
            "distribution": data.get("distribution"),
            "overall_score": data.get("overall_score"),
            "confidence": data.get("confidence"),
            "articles": [
                {
                    "url": a.get("url"),
                    "title": a.get("title"),
                    "source": a.get("source"),
                    "published_at": a.get("published_at"),
                    "sentiment": a.get("sentiment"),
                    "sentiment_score": a.get("sentiment_score"),
                }
                for a in (data.get("articles") or [])[:8]
            ],
        }
    if name == "market_data":
        return {
            k: data.get(k)
            for k in (
                "ticker",
                "company_name",
                "sector",
                "sector_etf",
                "price",
                "daily_change_pct",
                "volume",
                "market_cap",
                "pe_ratio",
                "fifty_two_week_high",
                "fifty_two_week_low",
                "last_two_quarterly_revenues",
                "delisted",
            )
        }
    if name == "correlation":
        return {
            k: data.get(k)
            for k in (
                "vs_sp500",
                "vs_sector_etf",
                "sector_etf_symbol",
                "vs_peers",
                "window_days",
            )
        }
    if name == "edgar_filings":
        return {"filings": (data.get("filings") or [])[:5]}
    if name == "peer_fundamentals":
        # `peers` here is a {ticker: fundamentals} mapping, not a list — cap by
        # picking the first 5 keys deterministically.
        peers_map = data.get("peers") or {}
        if isinstance(peers_map, dict):
            return {"peers": {k: peers_map[k] for k in list(peers_map.keys())[:5]}}
        return {"peers": peers_map[:5]}
    return data


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

            # news_sentiment + peer_news's _run() accept an optional budget
            # kwarg used for per-article sentiment classification.
            call_kwargs = dict(args)
            if name in ("news_sentiment", "peer_news"):
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
                    # Surface the structured result so the live UI can fill
                    # in market / correlation / sentiment cards as each tool
                    # completes (rather than all-at-once on `done`).
                    "data": _trim_for_stream(name, result.data) if result.ok else None,
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
                if name in ("news_sentiment", "peer_news"):
                    for a in result.data.get("articles", []):
                        url = a.get("url")
                        if url and url not in citation_urls:
                            citation_urls.append(url)
            else:
                errors.append(f"{name}:{result.status}:{result.error or ''}")
                # ANY non-ok tool result degrades the report — previously
                # only `budget_exceeded` did, which meant timeouts and
                # network errors silently produced reports that looked
                # complete. The synthesizer reads `degraded` to label the
                # output honestly.
                degraded = True
                reason = f"{name.upper()}_{(result.status or 'ERROR').upper()}"
                degradation_reason = (
                    reason
                    if not degradation_reason
                    else f"{degradation_reason};{reason}"
                )

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
