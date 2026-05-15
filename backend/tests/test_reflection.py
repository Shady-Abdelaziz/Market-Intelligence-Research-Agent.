"""Tests for the 3 brief-mandated reflection triggers."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.agent.nodes.reflection_critic import (
    trigger_neutral_sentiment,
    trigger_sector_correlation,
    trigger_stale_news,
)


def _state_with(tool_results: dict) -> dict:
    return {"tool_results": tool_results}


def test_sector_correlation_fires_above_threshold():
    fired, _ = trigger_sector_correlation(_state_with({"correlation": {"vs_sector_etf": 0.97}}))
    assert fired is True


def test_sector_correlation_does_not_fire_at_threshold():
    fired, _ = trigger_sector_correlation(_state_with({"correlation": {"vs_sector_etf": 0.95}}))
    assert fired is False


def test_sector_correlation_no_data():
    fired, _ = trigger_sector_correlation(_state_with({}))
    assert fired is False


def test_stale_news_all_old_fires():
    now = datetime.now(UTC)
    fired, _ = trigger_stale_news(
        _state_with(
            {
                "news_sentiment": {
                    "articles": [
                        {"published_at": (now - timedelta(hours=80)).isoformat()},
                        {"published_at": (now - timedelta(hours=96)).isoformat()},
                    ]
                }
            }
        )
    )
    assert fired is True


def test_stale_news_recent_does_not_fire():
    now = datetime.now(UTC)
    fired, _ = trigger_stale_news(
        _state_with(
            {
                "news_sentiment": {
                    "articles": [
                        {"published_at": (now - timedelta(hours=1)).isoformat()},
                        {"published_at": (now - timedelta(hours=80)).isoformat()},
                    ]
                }
            }
        )
    )
    assert fired is False


def test_stale_news_empty_articles_fires():
    fired, _ = trigger_stale_news(_state_with({"news_sentiment": {"articles": []}}))
    assert fired is True


def test_neutral_sentiment_perfectly_neutral_fires():
    fired, _ = trigger_neutral_sentiment(
        _state_with(
            {
                "news_sentiment": {
                    "distribution": {"positive": 0, "negative": 0, "neutral": 5, "total": 5}
                }
            }
        )
    )
    assert fired is True


def test_neutral_sentiment_evenly_split_fires():
    fired, _ = trigger_neutral_sentiment(
        _state_with(
            {
                "news_sentiment": {
                    "distribution": {"positive": 1, "negative": 1, "neutral": 3, "total": 5}
                }
            }
        )
    )
    assert fired is True


def test_neutral_sentiment_clear_skew_no_fire():
    fired, _ = trigger_neutral_sentiment(
        _state_with(
            {
                "news_sentiment": {
                    "distribution": {"positive": 4, "negative": 0, "neutral": 1, "total": 5}
                }
            }
        )
    )
    assert fired is False
