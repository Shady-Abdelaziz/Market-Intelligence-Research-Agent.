"""Compute 30-day rolling baselines for monitoring triggers."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

import yfinance as yf


@dataclass
class Baselines:
    mean: float
    std: float
    volume_avg: float
    last_close: float
    last_volume: int


def _compute_blocking(ticker: str, days: int = 30) -> Baselines:
    t = yf.Ticker(ticker)
    hist = t.history(period=f"{max(days + 10, 60)}d", interval="1d", auto_adjust=False)
    if hist.empty:
        raise ValueError(f"NO_HISTORY:{ticker}")
    hist = hist.tail(days)
    closes = hist["Close"].astype(float)
    volumes = hist["Volume"].astype(float)
    return Baselines(
        mean=float(closes.mean()),
        std=float(closes.std(ddof=0)),
        volume_avg=float(volumes.mean()),
        last_close=float(closes.iloc[-1]),
        last_volume=int(volumes.iloc[-1]),
    )


async def compute_baselines(ticker: str, days: int = 30) -> Baselines:
    return await asyncio.to_thread(_compute_blocking, ticker, days)
