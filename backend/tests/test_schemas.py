from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.api.schemas import (
    AnalysisReport,
    CorrelationAnalysis,
    DataFreshness,
    MarketSnapshot,
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
