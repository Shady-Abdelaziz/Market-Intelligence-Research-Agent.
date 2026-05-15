"""Tool 1: Market Data — structured market data via yfinance.

Returns exactly the 7 brief-mandated fields:
- price, daily_change_pct, volume, market_cap, pe_ratio, 52-week range,
  last two quarterly revenues.

yfinance is synchronous; we run it in a thread pool.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

import yfinance as yf

from app.cache.redis_cache import get as cache_get
from app.cache.redis_cache import set as cache_set
from app.config import get_settings
from app.tools.base import Tool

_settings = get_settings()

# Sector -> SPDR sector ETF mapping
SECTOR_ETF_MAP = {
    "Technology": "XLK",
    "Communication Services": "XLC",
    "Consumer Cyclical": "XLY",
    "Consumer Defensive": "XLP",
    "Energy": "XLE",
    "Financial Services": "XLF",
    "Healthcare": "XLV",
    "Industrials": "XLI",
    "Basic Materials": "XLB",
    "Real Estate": "XLRE",
    "Utilities": "XLU",
}


def _fetch_ticker_blocking(ticker: str) -> dict[str, Any]:
    t = yf.Ticker(ticker)
    info = t.info or {}
    if not info or not info.get("symbol") and not info.get("shortName"):
        raise ValueError(f"TICKER_NOT_FOUND:{ticker}")

    hist = t.history(period="2d", auto_adjust=False)
    price = None
    daily_change_pct = None
    volume = None
    if not hist.empty:
        last = hist.iloc[-1]
        price = float(last["Close"])
        volume = int(last["Volume"]) if last["Volume"] == last["Volume"] else 0
        if len(hist) > 1:
            prev = float(hist.iloc[-2]["Close"])
            if prev:
                daily_change_pct = ((price - prev) / prev) * 100.0

    # Quarterly revenues (last 2)
    quarterly_revenues = []
    try:
        qf = t.quarterly_financials
        if qf is not None and not qf.empty and "Total Revenue" in qf.index:
            rev_row = qf.loc["Total Revenue"].dropna()
            for date_col, rev in list(rev_row.items())[:2]:
                quarter = f"{date_col.year} Q{((date_col.month - 1) // 3) + 1}" if hasattr(date_col, "year") else str(date_col)
                quarterly_revenues.append(
                    {
                        "quarter": quarter,
                        "revenue_usd": float(rev) if rev == rev else None,
                        "reported_at": date_col.isoformat() if hasattr(date_col, "isoformat") else str(date_col),
                    }
                )
    except Exception:
        pass

    sector = info.get("sector")
    sector_etf = SECTOR_ETF_MAP.get(sector, "SPY")

    return {
        "ticker": ticker,
        "company_name": info.get("longName") or info.get("shortName") or ticker,
        "sector": sector,
        "sector_etf": sector_etf,
        "price": price,
        "daily_change_pct": daily_change_pct,
        "volume": volume,
        "market_cap": info.get("marketCap"),
        "pe_ratio": info.get("trailingPE"),
        "fifty_two_week_high": info.get("fiftyTwoWeekHigh"),
        "fifty_two_week_low": info.get("fiftyTwoWeekLow"),
        "last_two_quarterly_revenues": quarterly_revenues,
        "delisted": price is None and not quarterly_revenues,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }


class MarketDataTool(Tool):
    name = "market_data"
    upstream = "yfinance"

    def schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": (
                    "Fetch structured market data for a stock ticker: price, "
                    "daily change %, volume, market cap, P/E, 52-week range, "
                    "and the last two quarterly revenues. Also resolves sector "
                    "and the matching sector ETF."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "ticker": {"type": "string", "description": "Stock ticker symbol, e.g. 'TSLA'"},
                    },
                    "required": ["ticker"],
                },
            },
        }

    async def _run(self, ticker: str) -> dict[str, Any]:
        ticker = ticker.upper().strip()
        cached = await cache_get("yfinance", ticker)
        if cached:
            return cached
        data = await asyncio.to_thread(_fetch_ticker_blocking, ticker)
        await cache_set("yfinance", ticker, data, _settings.cache_ttl_yfinance)
        return data

    def summarize(self, output: dict[str, Any]) -> str:
        price = output.get("price")
        change = output.get("daily_change_pct")
        ticker = output.get("ticker")
        if price is None:
            return f"{ticker}: no current quote (possibly delisted)"
        change_str = f"{change:+.2f}%" if change is not None else "n/a"
        return f"{ticker} @ ${price:.2f} ({change_str})"
