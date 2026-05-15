"""Resolves a ticker symbol from the natural-language query.

Strategy:
1. If the query already has an uppercase token matching [A-Z]{1,5} that
   yfinance recognizes, use it.
2. Otherwise ask the LLM to extract a company name + ticker via a small
   structured-output call, then verify against yfinance.
3. On failure, set degraded=True with TICKER_NOT_FOUND.
"""

from __future__ import annotations

import asyncio
import json
import re

import yfinance as yf

from app.agent.events import emit
from app.agent.state import AgentState
from app.llm.budget import JobBudget
from app.llm.client import LLMClient
from app.observability.logging import get_logger
from app.tools.market_data import SECTOR_ETF_MAP

log = get_logger(__name__)

_TICKER_PATTERN = re.compile(r"\b([A-Z]{1,5})\b")


def _verify_ticker_blocking(candidate: str) -> dict | None:
    try:
        t = yf.Ticker(candidate)
        info = t.info or {}
        if info.get("symbol") or info.get("shortName") or info.get("longName"):
            return {
                "ticker": candidate,
                "company_name": info.get("longName") or info.get("shortName") or candidate,
                "sector": info.get("sector"),
                "sector_etf": SECTOR_ETF_MAP.get(info.get("sector"), "SPY"),
            }
    except Exception:
        return None
    return None


async def _verify_ticker(candidate: str) -> dict | None:
    return await asyncio.to_thread(_verify_ticker_blocking, candidate)


_EXTRACT_SYSTEM = """Extract the stock ticker symbol from a user query about a public company.
Output ONLY JSON: {"ticker": "TSLA", "company_name": "Tesla, Inc."}.
If you cannot determine a ticker, output: {"ticker": null, "company_name": null}."""


async def run(state: AgentState, llm_factory) -> AgentState:
    query = state["query"]
    job_id = state["job_id"]

    # Try regex first
    for match in _TICKER_PATTERN.findall(query):
        verified = await _verify_ticker(match)
        if verified:
            await emit(
                job_id,
                "ticker_resolved",
                {"ticker": verified["ticker"], "company_name": verified["company_name"], "method": "regex"},
            )
            return {**state, **verified, "peers": []}

    # Fall back to LLM
    budget = JobBudget.from_settings()
    llm: LLMClient = llm_factory(budget)
    try:
        resp = await llm.chat(
            messages=[
                {"role": "system", "content": _EXTRACT_SYSTEM},
                {"role": "user", "content": query},
            ],
            response_format={"type": "json_object"},
            temperature=0.0,
        )
        parsed = json.loads(resp.choices[0].message.content or "{}")
        candidate = (parsed.get("ticker") or "").upper().strip()
        if candidate:
            verified = await _verify_ticker(candidate)
            if verified:
                if parsed.get("company_name"):
                    verified["company_name"] = parsed["company_name"]
                await emit(
                    job_id,
                    "ticker_resolved",
                    {"ticker": verified["ticker"], "company_name": verified["company_name"], "method": "llm"},
                )
                return {**state, **verified, "peers": []}
    except Exception as e:
        log.warning("ticker_extraction_failed", error=str(e))

    await emit(job_id, "ticker_resolution_failed", {"query": query})
    return {
        **state,
        "ticker": None,
        "company_name": None,
        "degraded": True,
        "degradation_reason": "TICKER_NOT_FOUND",
        "errors": [*state.get("errors", []), "TICKER_NOT_FOUND"],
    }
