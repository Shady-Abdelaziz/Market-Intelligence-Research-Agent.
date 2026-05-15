"""Monitoring triggers — exactly per Section 12 of the build plan."""

from __future__ import annotations

from typing import Iterable

from app.persistence.models import MonitoringTarget


def trigger_new_articles(target: MonitoringTarget, current_article_hashes: Iterable[str]) -> bool:
    seen = set(target.last_seen_article_urls or [])
    new = [h for h in current_article_hashes if h not in seen]
    return len(new) >= 5


def trigger_price_2sigma(target: MonitoringTarget, today_close: float) -> bool:
    if target.baseline_price_mean is None or target.baseline_price_std is None:
        return False
    mean = float(target.baseline_price_mean)
    std = float(target.baseline_price_std)
    if std <= 0:
        return False
    return abs(today_close - mean) > 2.0 * std


def trigger_volume_2x(target: MonitoringTarget, today_volume: int) -> bool:
    if target.baseline_volume_avg is None:
        return False
    avg = float(target.baseline_volume_avg)
    if avg <= 0:
        return False
    return today_volume > 2.0 * avg
