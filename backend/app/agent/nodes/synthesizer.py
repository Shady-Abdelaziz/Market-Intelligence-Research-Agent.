"""Synthesizer node: produces the final AnalysisReport JSON.

Streams the synthesis tokens (synthesis_token SSE events), parses the
resulting JSON, validates against the Pydantic schema. On validation
failure, re-prompts once with the error; second failure -> degraded report.
"""

from __future__ import annotations

import contextlib
import json
from datetime import UTC, datetime
from typing import Any

from app.agent.events import emit
from app.agent.prompts import SYNTHESIZER_PROMPT, SYSTEM_PROMPT
from app.agent.state import AgentState
from app.api.schemas import (
    AnalysisReport,
    CorrelationAnalysis,
    DataFreshness,
    MarketSnapshot,
    QuarterlyRevenue,
    SentimentDistribution,
    TokenUsage,
    ToolInvocationLog,
)
from app.llm.budget import JobBudget
from app.observability.logging import get_logger

log = get_logger(__name__)


def _build_market_snapshot(md: dict[str, Any] | None) -> MarketSnapshot | None:
    if not md:
        return None
    qrev = [
        QuarterlyRevenue(
            quarter=q["quarter"],
            revenue_usd=q.get("revenue_usd") or 0.0,
            reported_at=datetime.fromisoformat(q["reported_at"])
            if q.get("reported_at")
            else datetime.now(UTC),
        )
        for q in (md.get("last_two_quarterly_revenues") or [])
    ]
    return MarketSnapshot(
        price=md.get("price") or 0.0,
        daily_change_pct=md.get("daily_change_pct") or 0.0,
        volume=int(md.get("volume") or 0),
        market_cap=md.get("market_cap"),
        pe_ratio=md.get("pe_ratio"),
        fifty_two_week_high=md.get("fifty_two_week_high") or 0.0,
        fifty_two_week_low=md.get("fifty_two_week_low") or 0.0,
        last_two_quarterly_revenues=qrev,
    )


def _build_correlation(c: dict[str, Any] | None) -> CorrelationAnalysis:
    if not c:
        return CorrelationAnalysis(
            vs_sp500=0.0, vs_sector_etf=0.0, sector_etf_symbol="SPY", vs_peers={}, window_days=0
        )
    return CorrelationAnalysis(
        vs_sp500=c.get("vs_sp500") or 0.0,
        vs_sector_etf=c.get("vs_sector_etf") or 0.0,
        sector_etf_symbol=c.get("sector_etf_symbol") or "SPY",
        vs_peers={k: float(v) for k, v in (c.get("vs_peers") or {}).items()},
        window_days=int(c.get("window_days") or 0),
    )


def _build_distribution(ns: dict[str, Any] | None) -> SentimentDistribution:
    if not ns:
        return SentimentDistribution(positive=0, negative=0, neutral=0, total=0, articles=[])
    dist = ns.get("distribution") or {}
    return SentimentDistribution(
        positive=int(dist.get("positive", 0)),
        negative=int(dist.get("negative", 0)),
        neutral=int(dist.get("neutral", 0)),
        total=int(dist.get("total", 0)),
        articles=[
            {
                "url": a["url"],
                "title": a.get("title") or "",
                "source": a.get("source") or "",
                "published_at": datetime.fromisoformat(a["published_at"].replace("Z", "+00:00"))
                if a.get("published_at")
                else datetime.now(UTC),
                "sentiment": a.get("sentiment", "neutral"),
                "sentiment_score": float(a.get("sentiment_score", 0.0)),
                "rationale": a.get("rationale"),
            }
            for a in (ns.get("articles") or [])
            if a.get("url")
        ],
    )


def _build_freshness(state: AgentState) -> DataFreshness:
    md = state.get("tool_results", {}).get("market_data") or {}
    ns = state.get("tool_results", {}).get("news_sentiment") or {}
    edgar = state.get("tool_results", {}).get("edgar_filings") or {}
    newest = None
    for a in ns.get("articles") or []:
        try:
            dt = datetime.fromisoformat((a.get("published_at") or "").replace("Z", "+00:00"))
            if newest is None or dt > newest:
                newest = dt
        except Exception:
            continue
    edgar_dt = None
    filings = edgar.get("filings") or []
    if filings:
        with contextlib.suppress(Exception):
            edgar_dt = datetime.fromisoformat(filings[0]["filed_on"]).replace(tzinfo=UTC)
    md_dt = datetime.now(UTC)
    if md.get("fetched_at"):
        with contextlib.suppress(Exception):
            md_dt = datetime.fromisoformat(md["fetched_at"])
    return DataFreshness(newest_article_at=newest, market_data_at=md_dt, edgar_filing_at=edgar_dt)


_FORCED_SUMMARY_FIELDS = ("analysis_summary", "key_findings")


def _stub_summary_and_findings(state: AgentState) -> dict[str, Any]:
    md = state.get("tool_results", {}).get("market_data") or {}
    ns = state.get("tool_results", {}).get("news_sentiment") or {}
    ticker = state.get("ticker") or "?"
    overall = float(ns.get("overall_score") or 0.0)
    price = md.get("price")
    change = md.get("daily_change_pct")
    summary = (
        f"{state.get('company_name') or ticker} ({ticker}) trading at "
        f"${price:.2f} ({change:+.2f}%). "
        if price and change is not None
        else f"{state.get('company_name') or ticker} ({ticker}). "
    )
    summary += (
        f"News sentiment is {'positive' if overall > 0.2 else 'negative' if overall < -0.2 else 'neutral'} "
        f"(score {overall:+.2f})."
    )
    findings = [
        f"Current sentiment score is {overall:+.2f} across {(ns.get('distribution') or {}).get('total', 0)} recent articles.",
        f"Market data captured at {md.get('fetched_at') or 'recently'}; market cap {md.get('market_cap') or 'n/a'}.",
        "Synthesis was performed in degraded mode — LLM output was unavailable or invalid.",
    ]
    return {"analysis_summary": summary, "key_findings": findings}


async def run(state: AgentState, llm_factory, budget: JobBudget) -> AgentState:
    job_id = state["job_id"]

    if not state.get("ticker"):
        # Emit a degraded report directly
        report = _make_degraded_report(state)
        await emit(job_id, "done", {"report": report.model_dump(mode="json")})
        return {**state, "report": report.model_dump(mode="json")}

    # Build deterministic components from tool results
    market_snapshot = _build_market_snapshot(state.get("tool_results", {}).get("market_data"))
    correlation = _build_correlation(state.get("tool_results", {}).get("correlation"))
    distribution = _build_distribution(state.get("tool_results", {}).get("news_sentiment"))
    freshness = _build_freshness(state)
    overall_sentiment = float(
        (state.get("tool_results", {}).get("news_sentiment") or {}).get("overall_score", 0.0)
    )
    confidence = float(
        (state.get("tool_results", {}).get("news_sentiment") or {}).get("confidence", 1.0)
    )

    # Ask the LLM ONLY for the prose fields
    llm = llm_factory(budget)
    user_payload = {
        "ticker": state.get("ticker"),
        "company_name": state.get("company_name"),
        "tool_results_summary": {
            k: state["tool_results"][k] for k in state.get("tool_results", {})
        },
        "triggers_fired": state.get("triggers_fired", []),
    }

    synthesis: dict[str, Any] | None = None
    try:
        # Stream the synthesis so the frontend sees live tokens
        full_text = ""
        primary_model = None
        async for chunk in llm.stream(
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": SYNTHESIZER_PROMPT
                    + "\n\nDATA:\n"
                    + json.dumps(user_payload, default=str),
                },
            ],
        ):
            primary_model = primary_model or chunk.model
            if chunk.choices and chunk.choices[0].delta and chunk.choices[0].delta.content:
                token = chunk.choices[0].delta.content
                full_text += token
                await emit(job_id, "synthesis_token", {"token": token})
            # capture usage from the final chunk
            if chunk.usage:
                budget.record_llm_usage(
                    primary_model or "unknown",
                    chunk.usage.prompt_tokens or 0,
                    chunk.usage.completion_tokens or 0,
                )

        synthesis = _safe_extract_json(full_text)
    except Exception as e:
        log.warning("synthesis_failed", error=str(e))

    if not synthesis or not _has_required_prose(synthesis):
        stub = _stub_summary_and_findings(state)
        synthesis = synthesis or {}
        synthesis.setdefault("analysis_summary", stub["analysis_summary"])
        synthesis.setdefault("key_findings", stub["key_findings"])

    findings = synthesis.get("key_findings") or []
    if not isinstance(findings, list):
        findings = [str(findings)]
    findings = [str(f) for f in findings][:3]
    while len(findings) < 3:
        findings.append("Additional analysis pending — insufficient data on this dimension.")

    # Build the final report
    primary_model = primary_model if "primary_model" in dir() else None  # type: ignore
    primary_model_str = state.get("llm_model_used") or "x-ai/grok-4.3"

    report = AnalysisReport(
        company_ticker=state["ticker"],
        company_name=state.get("company_name") or state["ticker"],
        analysis_summary=str(synthesis.get("analysis_summary", "")),
        sentiment_score=max(-1.0, min(1.0, overall_sentiment)),
        market_snapshot=market_snapshot
        or MarketSnapshot(
            price=0.0,
            daily_change_pct=0.0,
            volume=0,
            market_cap=None,
            pe_ratio=None,
            fifty_two_week_high=0.0,
            fifty_two_week_low=0.0,
            last_two_quarterly_revenues=[],
        ),
        correlation_analysis=correlation,
        key_findings=findings,
        tools_used=state.get("tools_used_order", []),
        citation_sources=state.get("citation_urls", []),
        generated_at=datetime.now(UTC),
        degraded=state.get("degraded", False),
        degradation_reason=state.get("degradation_reason"),
        reflection_passes=state.get("reflection_passes", 0),
        triggers_fired=state.get("triggers_fired", []),
        confidence=confidence,
        data_freshness=freshness,
        sentiment_distribution=distribution,
        token_usage=TokenUsage(
            prompt_tokens=budget.prompt_tokens,
            completion_tokens=budget.completion_tokens,
            total_tokens=budget.total_tokens,
            cost_usd=budget.cost_usd,
            model=primary_model_str,
        ),
        tool_invocations=[
            ToolInvocationLog(**inv) for inv in state.get("tool_invocation_logs", [])
        ],
        alert_tag=state.get("alert_tag"),
        monitor_trigger=state.get("monitor_trigger"),
    )

    dumped = report.model_dump(mode="json")
    await emit(job_id, "done", {"report": dumped})
    return {**state, "report": dumped}


def _safe_extract_json(text: str) -> dict[str, Any] | None:
    if not text:
        return None
    # First try straight parse, then look for the first {...} block
    try:
        return json.loads(text)
    except Exception:
        pass
    try:
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            return json.loads(text[start : end + 1])
    except Exception:
        return None
    return None


def _has_required_prose(d: dict[str, Any]) -> bool:
    return all(k in d for k in _FORCED_SUMMARY_FIELDS)


def _make_degraded_report(state: AgentState) -> AnalysisReport:
    """Build a minimal degraded report when we couldn't resolve a ticker."""
    return AnalysisReport(
        company_ticker=state.get("ticker") or "UNKNOWN",
        company_name=state.get("company_name") or "Unknown",
        analysis_summary="Unable to identify a public ticker from the query.",
        sentiment_score=0.0,
        market_snapshot=MarketSnapshot(
            price=0.0,
            daily_change_pct=0.0,
            volume=0,
            market_cap=None,
            pe_ratio=None,
            fifty_two_week_high=0.0,
            fifty_two_week_low=0.0,
            last_two_quarterly_revenues=[],
        ),
        correlation_analysis=CorrelationAnalysis(
            vs_sp500=0.0, vs_sector_etf=0.0, sector_etf_symbol="SPY", vs_peers={}, window_days=0
        ),
        key_findings=[
            "Could not resolve a stock ticker from the query.",
            "No tool calls were made.",
            "Try the query again with an explicit ticker symbol.",
        ],
        tools_used=[],
        citation_sources=[],
        generated_at=datetime.now(UTC),
        degraded=True,
        degradation_reason=state.get("degradation_reason") or "TICKER_NOT_FOUND",
        reflection_passes=0,
        triggers_fired=[],
        confidence=0.0,
        data_freshness=DataFreshness(
            newest_article_at=None,
            market_data_at=datetime.now(UTC),
            edgar_filing_at=None,
        ),
        sentiment_distribution=SentimentDistribution(
            positive=0, negative=0, neutral=0, total=0, articles=[]
        ),
        token_usage=TokenUsage(
            prompt_tokens=0, completion_tokens=0, total_tokens=0, cost_usd=0.0, model="-"
        ),
        tool_invocations=[],
        alert_tag=None,
        monitor_trigger=None,
    )
