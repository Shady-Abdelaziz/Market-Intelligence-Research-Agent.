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
    if not closes.notna().any() or not volumes.notna().any():
        raise ValueError(f"NO_DATA:{ticker}")
    mean = float(closes.mean())
    std = float(closes.std(ddof=0))
    volume_avg = float(volumes.mean())
    last_close = float(closes.iloc[-1])
    last_volume_raw = volumes.iloc[-1]
    # yfinance occasionally returns NaN on the most recent bar before the
    # daily close finalizes; refuse to register a monitor against bogus
    # numbers rather than letting a NaN poison the 2σ trigger downstream.
    if any(v != v for v in (mean, std, volume_avg, last_close)) or last_volume_raw != last_volume_raw:
        raise ValueError(f"NAN_BASELINE:{ticker}")
    return Baselines(
        mean=mean,
        std=std,
        volume_avg=volume_avg,
        last_close=last_close,
        last_volume=int(last_volume_raw),
    )


async def compute_baselines(ticker: str, days: int = 30) -> Baselines:
    return await asyncio.to_thread(_compute_blocking, ticker, days)
