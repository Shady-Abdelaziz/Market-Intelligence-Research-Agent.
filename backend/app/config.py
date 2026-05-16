"""Application configuration loaded from environment variables.

All settings are typed via Pydantic and centralized here so the rest of the
codebase never reads os.environ directly.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore", case_sensitive=False
    )

    # LLM
    openrouter_api_key: str = ""
    llm_primary_model: str = "x-ai/grok-4.3"
    llm_temperature: float = 0.2
    llm_max_tokens: int = 4096
    llm_request_timeout_seconds: int = 120
    llm_prompt_cache_enabled: bool = True

    # External data APIs
    newsapi_key: str = ""
    marketaux_key: str = ""
    alphavantage_key: str = ""
    finnhub_key: str = ""
    edgar_user_agent: str = "MIRA Agent contact@example.com"

    # Database
    database_url: str = "sqlite+aiosqlite:///./mira.db"

    # Redis
    redis_url: str = ""

    # Agent budget
    max_tool_calls: int = 10
    max_reflection_passes: int = 2
    max_tokens_per_job: int = 200_000

    # Monitoring
    monitor_default_cadence_seconds: int = 86_400
    monitor_baseline_window_days: int = 30
    monitor_trading_calendar: str = "NYSE"

    # Reflection thresholds
    reflection_sector_corr_threshold: float = 0.95
    reflection_stale_news_hours: int = 72
    reflection_analysis_window_days: int = 90

    # Cache TTLs (seconds)
    cache_ttl_yfinance: int = 300
    cache_ttl_news: int = 3600
    cache_ttl_edgar: int = 86_400

    # Circuit breakers
    breaker_fail_max: int = 5
    breaker_reset_timeout_seconds: int = 60

    # Rate limits
    ratelimit_analyze: str = "10/minute"
    ratelimit_monitor: str = "5/minute"

    # API
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    frontend_origin: str = "http://localhost:3000"
    # Comma-separated list of additional allowed origins for CORS. If empty,
    # the allowlist is just [frontend_origin]. Never a wildcard with
    # allow_credentials=True (browsers reject that combination, and it
    # nullifies the allowlist's security intent).
    cors_origins: str = ""
    log_level: str = "INFO"
    log_format: Literal["json", "console"] = "json"

    @property
    def redis_enabled(self) -> bool:
        return bool(self.redis_url)

    @property
    def cors_allow_origins(self) -> list[str]:
        extra = [o.strip() for o in self.cors_origins.split(",") if o.strip()]
        # Preserve order, dedupe.
        seen: set[str] = set()
        out: list[str] = []
        for o in [self.frontend_origin, *extra]:
            if o and o not in seen:
                seen.add(o)
                out.append(o)
        return out

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
