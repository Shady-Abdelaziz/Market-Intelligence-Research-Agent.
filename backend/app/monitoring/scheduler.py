"""Trading-day awareness for monitoring cron."""

from __future__ import annotations

from datetime import date, datetime

try:
    import pandas_market_calendars as mcal  # type: ignore

    _HAS_MCAL = True
except Exception:  # pragma: no cover
    _HAS_MCAL = False

from app.config import get_settings


def is_trading_day(dt: datetime | None = None) -> bool:
    """Return True if the date is a trading day on the configured calendar."""
    when: date = (dt or datetime.utcnow()).date()
    if not _HAS_MCAL:
        # Conservative fallback: weekday and not a US fixed holiday list
        return when.weekday() < 5
    cal = mcal.get_calendar(get_settings().monitor_trading_calendar)
    sched = cal.schedule(start_date=when.isoformat(), end_date=when.isoformat())
    return not sched.empty
