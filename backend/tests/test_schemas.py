from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.api.schemas import (
    AnalysisReport,
    ArticleSentiment,
    CorrelationAnalysis,
    DataFreshness,
    MarketSnapshot,
    MonitorStartRequest,
    SentimentDistribution,
    TokenUsage,
)


def _minimal_report(**overrides):
    base = {
        "company_ticker": "TSLA",
        "company_name": "Tesla, Inc.",
        "analysis_summary": "ok",
        "sentiment_score": 0.2,
        "market_snapshot": MarketSnapshot(
            price=100,
            daily_change_pct=1.0,
            volume=100,
            market_cap=1e10,
            pe_ratio=20.0,
            fifty_two_week_high=120,
            fifty_two_week_low=80,
            last_two_quarterly_revenues=[],
        ),
        "correlation_analysis": CorrelationAnalysis(
            vs_sp500=0.5, vs_sector_etf=0.7, sector_etf_symbol="XLY", vs_peers={}, window_days=90
        ),
        "key_findings": ["a", "b", "c"],
        "tools_used": ["market_data"],
        "citation_sources": [],
        "generated_at": datetime.now(UTC),
        "data_freshness": DataFreshness(
            newest_article_at=None,
            market_data_at=datetime.now(UTC),
            edgar_filing_at=None,
        ),
        "sentiment_distribution": SentimentDistribution(
            positive=0, negative=0, neutral=0, total=0, articles=[]
        ),
        "token_usage": TokenUsage(
            prompt_tokens=0,
            completion_tokens=0,
            total_tokens=0,
            cost_usd=0.0,
            model="x-ai/grok-4.3",
        ),
        "tool_invocations": [],
    }
    base.update(overrides)
    return AnalysisReport(**base)


def test_minimal_report_validates():
    r = _minimal_report()
    assert r.company_ticker == "TSLA"


def test_key_findings_must_be_exactly_three():
    with pytest.raises(ValidationError):
        _minimal_report(key_findings=["only one"])
    with pytest.raises(ValidationError):
        _minimal_report(key_findings=["a", "b", "c", "d"])


def test_sentiment_score_bounded():
    with pytest.raises(ValidationError):
        _minimal_report(sentiment_score=1.5)
    with pytest.raises(ValidationError):
        _minimal_report(sentiment_score=-2.0)


def test_proactive_alert_tag_and_monitor_trigger_propagate():
    """Brief §3B: monitor-triggered analyses must be marked PROACTIVE_ALERT
    and the firing trigger must be recorded."""
    r = _minimal_report(alert_tag="PROACTIVE_ALERT", monitor_trigger="price_2sigma")
    assert r.alert_tag == "PROACTIVE_ALERT"
    assert r.monitor_trigger == "price_2sigma"
    dumped = r.model_dump(mode="json")
    assert dumped["alert_tag"] == "PROACTIVE_ALERT"
    assert dumped["monitor_trigger"] == "price_2sigma"


def test_monitor_trigger_rejects_unknown_values():
    with pytest.raises(ValidationError):
        _minimal_report(monitor_trigger="not_a_real_trigger")


def test_correlation_analysis_allows_none_for_index_and_sector():
    """vs_sp500 / vs_sector_etf can be None when there isn't enough
    overlapping return history. A 0.0 default would be indistinguishable
    from a real low correlation and would mask the reflection trigger's
    "skip" branch."""
    c = CorrelationAnalysis(
        vs_sp500=None,
        vs_sector_etf=None,
        sector_etf_symbol="SPY",
        vs_peers={},
        window_days=0,
    )
    dumped = c.model_dump(mode="json")
    assert dumped["vs_sp500"] is None
    assert dumped["vs_sector_etf"] is None
    roundtrip = CorrelationAnalysis.model_validate(dumped)
    assert roundtrip.vs_sp500 is None
    assert roundtrip.vs_sector_etf is None


def test_monitor_start_request_cadence_floor():
    """1 h floor — below that, the monitor would hammer yfinance + NewsAPI
    past their free-tier limits and the brief frames monitoring as a
    background cadence, not realtime."""
    with pytest.raises(ValidationError):
        MonitorStartRequest(ticker="AAPL", cadence_seconds=60)
    with pytest.raises(ValidationError):
        MonitorStartRequest(ticker="AAPL", cadence_seconds=3599)
    # Exactly 3600 (1 h) is the floor and must pass.
    ok = MonitorStartRequest(ticker="AAPL", cadence_seconds=3600)
    assert ok.cadence_seconds == 3600


def test_article_sentiment_allows_optional_metadata():
    """News tool can return None for title/source/published_at; schema must accept it."""
    a = ArticleSentiment(
        url="https://example.com/x",
        title=None,
        source=None,
        published_at=None,
        sentiment="neutral",
        sentiment_score=0.0,
    )
    assert a.title is None
    assert a.source is None
    assert a.published_at is None

    dumped = a.model_dump(mode="json")
    assert dumped["title"] is None
    assert dumped["source"] is None
    assert dumped["published_at"] is None

    roundtrip = ArticleSentiment.model_validate(dumped)
    assert roundtrip.title is None
    assert roundtrip.source is None
    assert roundtrip.published_at is None
