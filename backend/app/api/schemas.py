"""Pydantic v2 schemas — API request/response shapes."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class AnalyzeRequest(BaseModel):
    query: str = Field(min_length=1, max_length=2000)


class AnalyzeResponse(BaseModel):
    job_id: str
    status: str


class MonitorStartRequest(BaseModel):
    ticker: str = Field(min_length=1, max_length=16)
    # 1 h floor: ticks below this hammer yfinance + NewsAPI past their
    # free-tier rate limits, and the brief frames monitoring as a
    # background cadence (default 24 h, trading-day-aware), not a
    # near-realtime poll. Tests assert this rejects sub-hour values.
    cadence_seconds: int = Field(default=86_400, ge=3600)
    peers: list[str] = Field(default_factory=list)


class MonitorRecord(BaseModel):
    id: str
    ticker: str
    cadence_seconds: int
    peers: list[str] = Field(default_factory=list)
    active: bool
    last_run_at: datetime | None
    baseline_price_mean: float | None
    baseline_price_std: float | None
    baseline_volume_avg: float | None


class QuarterlyRevenue(BaseModel):
    quarter: str
    revenue_usd: float
    reported_at: datetime


class MarketSnapshot(BaseModel):
    price: float
    daily_change_pct: float
    volume: int
    market_cap: float | None
    pe_ratio: float | None
    fifty_two_week_high: float
    fifty_two_week_low: float
    last_two_quarterly_revenues: list[QuarterlyRevenue]


class CorrelationAnalysis(BaseModel):
    # Optional — the correlation tool returns None when there isn't enough
    # overlapping return history (delisted ETF, illiquid peer, freshly
    # IPO'd ticker, zero variance). 0.0 would be indistinguishable from
    # a real low correlation; the reflection trigger relies on the None
    # signal to skip the 0.95 check.
    vs_sp500: float | None
    vs_sector_etf: float | None
    sector_etf_symbol: str
    vs_peers: dict[str, float]
    window_days: int


class ArticleSentiment(BaseModel):
    url: str
    title: str | None = None
    source: str | None = None
    published_at: datetime | None = None
    sentiment: Literal["positive", "negative", "neutral"]
    sentiment_score: float
    rationale: str | None = None


class SentimentDistribution(BaseModel):
    positive: int
    negative: int
    neutral: int
    total: int
    articles: list[ArticleSentiment]


class ToolInvocationLog(BaseModel):
    name: str
    input: dict
    output_summary: str
    latency_ms: int
    status: str


class TokenUsage(BaseModel):
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    cost_usd: float
    model: str


class DataFreshness(BaseModel):
    newest_article_at: datetime | None
    market_data_at: datetime
    edgar_filing_at: datetime | None


class ExtendedAnalysis(BaseModel):
    """Optional richer analyst-style block. The synthesizer fills any field
    it can ground in tool results and leaves the rest null. Existing reports
    in Postgres deserialize fine because every field is optional."""

    bull_case: str | None = None
    bear_case: str | None = None
    catalysts: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    valuation_context: str | None = None


class AnalysisReport(BaseModel):
    model_config = ConfigDict(json_schema_extra={"title": "M.I.R.A. Analysis Report"})

    # === BRIEF-MANDATED MINIMUM FIELDS ===
    company_ticker: str
    company_name: str
    analysis_summary: str
    sentiment_score: float = Field(ge=-1.0, le=1.0)
    market_snapshot: MarketSnapshot
    correlation_analysis: CorrelationAnalysis
    key_findings: list[str]
    tools_used: list[str]
    citation_sources: list[str]
    generated_at: datetime

    # === EXTRA FIELDS ===
    degraded: bool = False
    degradation_reason: str | None = None
    reflection_passes: int = 0
    triggers_fired: list[str] = Field(default_factory=list)
    confidence: float = 1.0
    data_freshness: DataFreshness
    sentiment_distribution: SentimentDistribution
    token_usage: TokenUsage
    tool_invocations: list[ToolInvocationLog]
    alert_tag: Literal["PROACTIVE_ALERT"] | None = None
    monitor_trigger: Literal["articles", "price_2sigma", "volume_2x"] | None = None
    extended_analysis: ExtendedAnalysis | None = None

    @field_validator("key_findings")
    @classmethod
    def _exactly_three(cls, v: list[str]) -> list[str]:
        if len(v) != 3:
            raise ValueError("key_findings must contain exactly 3 items")
        return v
