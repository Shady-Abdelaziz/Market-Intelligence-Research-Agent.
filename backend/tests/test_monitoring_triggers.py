"""Tests for the 3 brief-mandated monitoring triggers."""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.monitoring.triggers import (
    trigger_new_articles,
    trigger_price_2sigma,
    trigger_volume_2x,
)


def _target(**kwargs):
    base = {
        "last_seen_article_urls": [],
        "baseline_price_mean": Decimal("100"),
        "baseline_price_std": Decimal("5"),
        "baseline_volume_avg": Decimal("1000000"),
    }
    base.update(kwargs)
    return SimpleNamespace(**base)


def test_articles_fires_at_5_new():
    t = _target(last_seen_article_urls=["a", "b"])
    assert trigger_new_articles(t, ["c", "d", "e", "f", "g"]) is True


def test_articles_does_not_fire_at_4_new():
    t = _target(last_seen_article_urls=["a"])
    assert trigger_new_articles(t, ["a", "b", "c", "d", "e"]) is False  # only 4 new


def test_price_2sigma_fires_above():
    t = _target()
    assert trigger_price_2sigma(t, today_close=120.0) is True  # +4σ


def test_price_2sigma_does_not_fire_inside():
    t = _target()
    assert trigger_price_2sigma(t, today_close=108.0) is False  # +1.6σ


def test_volume_2x_fires():
    t = _target()
    assert trigger_volume_2x(t, today_volume=2_500_000) is True


def test_volume_2x_does_not_fire_at_threshold():
    t = _target()
    assert trigger_volume_2x(t, today_volume=2_000_000) is False
