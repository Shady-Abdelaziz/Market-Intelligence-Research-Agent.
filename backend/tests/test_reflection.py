"""Tests for the 3 brief-mandated reflection triggers."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.agent.nodes import reflection_critic
from app.agent.nodes.reflection_critic import (
    trigger_neutral_sentiment,
    trigger_sector_correlation,
    trigger_stale_news,
)
from app.agent.utils.dates import parse_published_at


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


def test_stale_news_mixed_formats_fires_only_when_all_parseable_old():
    now = datetime.now(UTC)
    old_z = (now - timedelta(hours=80)).isoformat().replace("+00:00", "Z")
    old_offset = (now - timedelta(hours=96)).isoformat()  # has +00:00
    old_naive = (now - timedelta(hours=120)).replace(tzinfo=None).isoformat()
    old_epoch = int((now - timedelta(hours=200)).timestamp())
    fired, reasoning = trigger_stale_news(
        _state_with(
            {
                "news_sentiment": {
                    "articles": [
                        {"published_at": old_z},
                        {"published_at": old_offset},
                        {"published_at": old_naive},
                        {"published_at": old_epoch},
                        {"published_at": "not-a-date"},
                        {"published_at": None},
                    ]
                }
            }
        )
    )
    assert fired is True
    assert "older than" in reasoning


def test_stale_news_mixed_formats_recent_does_not_fire():
    now = datetime.now(UTC)
    old_z = (now - timedelta(hours=80)).isoformat().replace("+00:00", "Z")
    recent_offset = (now - timedelta(hours=1)).isoformat()
    fired, _ = trigger_stale_news(
        _state_with(
            {
                "news_sentiment": {
                    "articles": [
                        {"published_at": old_z},
                        {"published_at": recent_offset},
                        {"published_at": "garbage"},
                    ]
                }
            }
        )
    )
    assert fired is False


def test_parse_published_at_handles_common_inputs():
    assert parse_published_at(None) is None
    assert parse_published_at("") is None
    assert parse_published_at("not-a-date") is None
    assert parse_published_at(True) is None  # bool not treated as epoch

    z = parse_published_at("2024-01-02T03:04:05Z")
    assert z is not None and z.tzinfo is not None
    assert z.year == 2024 and z.month == 1 and z.hour == 3

    off = parse_published_at("2024-01-02T03:04:05+00:00")
    assert off == z

    naive = parse_published_at("2024-01-02T03:04:05")
    assert naive is not None and naive.tzinfo is not None
    assert naive == z

    epoch_int = parse_published_at(0)
    assert epoch_int == datetime(1970, 1, 1, tzinfo=UTC)

    epoch_float = parse_published_at(0.0)
    assert epoch_float == datetime(1970, 1, 1, tzinfo=UTC)

    aware_dt = datetime(2024, 1, 2, 3, 4, 5, tzinfo=UTC)
    assert parse_published_at(aware_dt) is aware_dt

    naive_dt = datetime(2024, 1, 2, 3, 4, 5)
    out = parse_published_at(naive_dt)
    assert out is not None and out.tzinfo is UTC


@pytest.mark.asyncio
async def test_triggers_fired_payload_uses_backend_keys(monkeypatch):
    """Lock the wire-format trigger names so a rename can't silently break the frontend."""
    emitted: list[tuple[str, dict]] = []

    async def fake_emit(job_id, event, payload):
        emitted.append((event, payload))

    monkeypatch.setattr(reflection_critic, "emit", fake_emit)
    monkeypatch.setattr(
        reflection_critic.reflection_pass_metric, "observe", lambda *_a, **_k: None
    )

    now = datetime.now(UTC)
    state = {
        "job_id": "test-job",
        "tool_results": {
            "correlation": {"vs_sector_etf": 0.99},
            "news_sentiment": {
                "articles": [
                    {"published_at": (now - timedelta(hours=200)).isoformat()},
                ],
                "distribution": {"positive": 0, "negative": 0, "neutral": 3, "total": 3},
            },
        },
    }
    out = await reflection_critic.run(state)
    fired = set(out["triggers_fired"])
    assert fired == {"sector_correlation", "stale_news", "neutral_sentiment"}

    replans = [p for ev, p in emitted if ev == "replan"]
    assert replans, "expected a replan event"
    assert set(replans[0]["triggers_fired"]) <= {
        "sector_correlation",
        "stale_news",
        "neutral_sentiment",
    }
