"""Tool 3 (correlation half): real Pearson correlation of returns vs S&P 500,
sector ETF, and named peers, over a configurable trailing window of
trading days. Uses yfinance OHLC; no LLM involvement.
"""

from __future__ import annotations

import asyncio
from typing import Any

import numpy as np
import pandas as pd
import yfinance as yf

from app.config import get_settings
from app.tools.base import Tool

_settings = get_settings()


def _download_blocking(symbols: list[str], days: int) -> pd.DataFrame:
    period = f"{max(days + 30, 120)}d"
    df = yf.download(
        symbols, period=period, interval="1d", auto_adjust=True, progress=False, threads=False
    )
    if isinstance(df.columns, pd.MultiIndex):
        df = df["Close"]
    else:
        df = df[["Close"]]
        df.columns = symbols
    return df.dropna(how="all")


def _pearson(a: pd.Series, b: pd.Series) -> float | None:
    paired = pd.concat([a, b], axis=1).dropna()
    if len(paired) < 5:
        return None
    a2, b2 = paired.iloc[:, 0], paired.iloc[:, 1]
    if a2.std() == 0 or b2.std() == 0:
        return None
    return float(np.corrcoef(a2, b2)[0, 1])


def _compute_correlations(
    ticker: str, sector_etf: str, peers: list[str], window_days: int
) -> dict[str, Any]:
    symbols = list({ticker, "SPY", sector_etf, *peers})
    closes = _download_blocking(symbols, window_days)
    if ticker not in closes.columns or closes[ticker].dropna().empty:
        raise ValueError(f"TICKER_DATA_UNAVAILABLE:{ticker}")
    closes = closes.tail(window_days)
    returns = closes.pct_change().dropna(how="all")

    base = returns.get(ticker)
    if base is None or base.empty:
        raise ValueError(f"TICKER_DATA_UNAVAILABLE:{ticker}")

    vs_sp500 = _pearson(base, returns.get("SPY", pd.Series(dtype=float)))
    vs_sector = _pearson(base, returns.get(sector_etf, pd.Series(dtype=float)))
    vs_peers: dict[str, float] = {}
    for p in peers:
        c = _pearson(base, returns.get(p, pd.Series(dtype=float)))
        if c is not None:
            vs_peers[p] = c

    return {
        # Pass None through unchanged so downstream consumers can distinguish
        # "unavailable" (e.g. insufficient overlapping bars, zero variance)
        # from a real low correlation. The reflection trigger already treats
        # None as "skip"; the schema marks both fields Optional.
        "vs_sp500": vs_sp500,
        "vs_sector_etf": vs_sector,
        "sector_etf_symbol": sector_etf,
        "vs_peers": vs_peers,
        "window_days": window_days,
    }


class CorrelationTool(Tool):
    name = "correlation"
    upstream = "yfinance"

    def schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": (
                    "Compute Pearson correlation of daily returns for the "
                    "target ticker against the S&P 500 (SPY), its sector ETF, "
                    "and a list of peer tickers, over the trailing N trading days."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "ticker": {"type": "string"},
                        "sector_etf": {
                            "type": "string",
                            "description": "e.g. XLK, XLE, defaults to SPY",
                        },
                        "peers": {"type": "array", "items": {"type": "string"}},
                        "window_days": {"type": "integer", "default": 90},
                    },
                    "required": ["ticker"],
                },
            },
        }

    async def _run(
        self,
        ticker: str,
        sector_etf: str = "SPY",
        peers: list[str] | None = None,
        window_days: int | None = None,
    ) -> dict[str, Any]:
        ticker = ticker.upper().strip()
        peers = [p.upper().strip() for p in (peers or [])]
        window_days = window_days or _settings.reflection_analysis_window_days
        if not sector_etf:
            sector_etf = "SPY"
        return await asyncio.to_thread(
            _compute_correlations, ticker, sector_etf, peers, window_days
        )

    def summarize(self, output: dict[str, Any]) -> str:
        return (
            f"vs SPY={output['vs_sp500']:.2f}, "
            f"vs {output['sector_etf_symbol']}={output['vs_sector_etf']:.2f}, "
            f"peers={list(output['vs_peers'].keys())}"
        )
