"""POST /resolve_tickers — validate or LLM-correct user-supplied tickers / company names.

Used by the monitor form so a user can type "tesla" or "aapl " or "GOOGLE"
and get back a verified US-listed ticker. Inputs that the LLM cannot map to
any plausible US-listed equity are returned with status="invalid".
"""

from __future__ import annotations

import asyncio
import json
from typing import Literal

import yfinance as yf
from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from app.llm.budget import JobBudget
from app.llm.client import LLMClient
from app.observability.logging import get_logger
from app.observability.ratelimit import limiter
from app.config import get_settings

router = APIRouter(tags=["resolve"])
log = get_logger(__name__)
_settings = get_settings()


class ResolveRequest(BaseModel):
    inputs: list[str] = Field(min_length=1, max_length=16)


class ResolvedItem(BaseModel):
    input: str
    status: Literal["ok", "corrected", "invalid"]
    ticker: str | None = None
    company_name: str | None = None
    message: str | None = None


class ResolveResponse(BaseModel):
    results: list[ResolvedItem]


# US-listed exchanges yfinance reports. yfinance is inconsistent about
# `country` (sometimes missing on ADRs / dual listings), so prefer the
# exchange code when present.
_US_EXCHANGES = {
    "NMS", "NGM", "NCM",   # Nasdaq tiers
    "NYQ",                  # NYSE
    "ASE", "AMX",           # NYSE American
    "PCX", "BATS", "BTS",   # ARCA / Cboe BZX
    "OQB", "OQX", "PNK",    # OTC tiers
}


def _verify_blocking(candidate: str) -> dict | None:
    try:
        t = yf.Ticker(candidate)
        info = t.info or {}
    except Exception:
        return None
    symbol = info.get("symbol")
    name = info.get("longName") or info.get("shortName")
    if not (symbol or name):
        return None
    exchange = (info.get("exchange") or "").upper()
    country = (info.get("country") or "").strip()
    us_listed = exchange in _US_EXCHANGES or country == "United States"
    if not us_listed:
        return None
    return {
        "ticker": (symbol or candidate).upper(),
        "company_name": name or candidate,
    }


async def _verify(candidate: str) -> dict | None:
    return await asyncio.to_thread(_verify_blocking, candidate)


_RESOLVE_SYSTEM = """You map a user's free-form input to a US-listed stock ticker.
The input may be a ticker (possibly mistyped or lowercase), a company name, or a brand.
Output ONLY JSON: {"ticker": "TSLA", "company_name": "Tesla, Inc."}.
The ticker MUST be a real US-listed equity (NYSE, Nasdaq, NYSE American, ARCA, Cboe, OTC).
If the input does not plausibly refer to any US-listed public company, output:
{"ticker": null, "company_name": null}."""


async def _resolve_one(raw: str) -> ResolvedItem:
    original = raw.strip()
    if not original:
        return ResolvedItem(input=raw, status="invalid", message="Empty input.")

    # Fast path: try the input as a literal ticker.
    upper = original.upper()
    verified = await _verify(upper)
    if verified:
        return ResolvedItem(
            input=original,
            status="ok" if verified["ticker"] == upper else "corrected",
            ticker=verified["ticker"],
            company_name=verified["company_name"],
        )

    # LLM fallback — let it correct typos or map company name -> ticker.
    budget = JobBudget.from_settings()
    llm = LLMClient(budget)
    try:
        resp = await llm.chat(
            messages=[
                {"role": "system", "content": _RESOLVE_SYSTEM},
                {"role": "user", "content": original},
            ],
            response_format={"type": "json_object"},
            temperature=0.0,
        )
        parsed = json.loads(resp.choices[0].message.content or "{}")
    except Exception as e:  # noqa: BLE001
        log.warning("resolve_llm_failed", input=original, error=str(e))
        return ResolvedItem(
            input=original,
            status="invalid",
            message="Couldn't resolve to a US-listed ticker. Please check the symbol or company name.",
        )

    candidate = (parsed.get("ticker") or "").upper().strip()
    if not candidate:
        return ResolvedItem(
            input=original,
            status="invalid",
            message=f'"{original}" doesn\'t match any US-listed public company.',
        )

    verified = await _verify(candidate)
    if not verified:
        return ResolvedItem(
            input=original,
            status="invalid",
            message=f'"{original}" doesn\'t match any US-listed public company.',
        )
    if parsed.get("company_name"):
        verified["company_name"] = parsed["company_name"]
    return ResolvedItem(
        input=original,
        status="corrected",
        ticker=verified["ticker"],
        company_name=verified["company_name"],
    )


@router.post("/resolve_tickers", response_model=ResolveResponse)
@limiter.limit(_settings.ratelimit_analyze)
async def resolve_tickers(request: Request, req: ResolveRequest) -> ResolveResponse:
    results = await asyncio.gather(*(_resolve_one(i) for i in req.inputs))
    return ResolveResponse(results=list(results))
