"""SQLAlchemy 2.0 ORM models.

Mirror the DDL in Section 7 of the build plan. Uses generic types that map
cleanly to both Postgres (JSONB, TIMESTAMPTZ, ARRAY, UUID) and SQLite (JSON,
DATETIME, string-serialized arrays, char(36)).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    ARRAY,
    JSON,
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def _uuid_default():
    """Return a uuid as a string — portable across Postgres + SQLite drivers.

    Postgres' UUID adapter handles strings fine; aiosqlite cannot bind
    uuid.UUID objects directly.
    """
    return str(uuid.uuid4())


def _uuid_col() -> Mapped[str]:
    """Portable UUID PK column (native UUID on Postgres, char(36) on SQLite)."""
    return mapped_column(
        UUID(as_uuid=False).with_variant(String(36), "sqlite"),
        primary_key=True,
        default=_uuid_default,
    )


def _json_col(nullable: bool = True, default=None) -> Mapped:
    return mapped_column(
        JSONB().with_variant(JSON(), "sqlite"),
        nullable=nullable,
        default=default,
    )


def _array_text_col(default_factory=list):
    """Portable text[] (uses Postgres ARRAY natively, JSON list on SQLite)."""
    return mapped_column(
        ARRAY(Text).with_variant(JSON(), "sqlite"),
        nullable=False,
        default=default_factory,
    )


class Base(DeclarativeBase):
    pass


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[uuid.UUID] = _uuid_col()
    query: Mapped[str] = mapped_column(Text, nullable=False)
    ticker: Mapped[str | None] = mapped_column(String(16), index=True, nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    result_json = _json_col()
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[Decimal] = mapped_column(Numeric(10, 6), default=Decimal("0"))
    tool_calls_count: Mapped[int] = mapped_column(Integer, default=0)
    reflection_passes: Mapped[int] = mapped_column(Integer, default=0)
    alert_tag: Mapped[str | None] = mapped_column(String(32), nullable=True)
    monitor_target_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=False).with_variant(String(36), "sqlite"),
        ForeignKey("monitoring_targets.id", ondelete="SET NULL"),
        nullable=True,
    )
    triggers_fired = _array_text_col()

    tool_invocations: Mapped[list[ToolInvocation]] = relationship(
        back_populates="job", cascade="all, delete-orphan"
    )
    llm_calls: Mapped[list[LLMCall]] = relationship(
        back_populates="job", cascade="all, delete-orphan"
    )
    events: Mapped[list[AgentEvent]] = relationship(
        back_populates="job", cascade="all, delete-orphan", order_by="AgentEvent.id"
    )


class MonitoringTarget(Base):
    __tablename__ = "monitoring_targets"

    id: Mapped[uuid.UUID] = _uuid_col()
    ticker: Mapped[str] = mapped_column(String(16), nullable=False, unique=True)
    cadence_seconds: Mapped[int] = mapped_column(Integer, default=86_400, nullable=False)
    peers = _array_text_col()
    baseline_price_mean: Mapped[Decimal | None] = mapped_column(Numeric(14, 4), nullable=True)
    baseline_price_std: Mapped[Decimal | None] = mapped_column(Numeric(14, 4), nullable=True)
    baseline_volume_avg: Mapped[Decimal | None] = mapped_column(Numeric(20, 2), nullable=True)
    baselines_computed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_seen_article_urls = _array_text_col()
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class ToolInvocation(Base):
    __tablename__ = "tool_invocations"

    id: Mapped[uuid.UUID] = _uuid_col()
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=False).with_variant(String(36), "sqlite"),
        ForeignKey("jobs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    tool_name: Mapped[str] = mapped_column(String(64), nullable=False)
    input_json = _json_col(nullable=False, default=dict)
    output_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    job: Mapped[Job] = relationship(back_populates="tool_invocations")


class LLMCall(Base):
    __tablename__ = "llm_calls"

    id: Mapped[uuid.UUID] = _uuid_col()
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=False).with_variant(String(36), "sqlite"),
        ForeignKey("jobs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    model: Mapped[str] = mapped_column(String(128), nullable=False)
    prompt_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    completion_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    cost_usd: Mapped[Decimal] = mapped_column(Numeric(10, 6), nullable=False)
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    cached: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    job: Mapped[Job] = relationship(back_populates="llm_calls")


class Article(Base):
    __tablename__ = "articles"

    url_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    title_fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source: Mapped[str | None] = mapped_column(String(255), nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ticker: Mapped[str | None] = mapped_column(String(16), nullable=True)
    raw_json = _json_col()
    sentiment_label: Mapped[str | None] = mapped_column(String(16), nullable=True)
    sentiment_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 4), nullable=True)
    cached_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (Index("idx_articles_ticker_pub", "ticker", "published_at"),)


class AgentEvent(Base):
    __tablename__ = "agent_events"

    # Use Integer (with BigInteger variant on Postgres) — SQLite only auto-
    # increments INTEGER PRIMARY KEY, not BIGINT.
    id: Mapped[int] = mapped_column(
        Integer().with_variant(BigInteger(), "postgresql"),
        primary_key=True,
        autoincrement=True,
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=False).with_variant(String(36), "sqlite"),
        ForeignKey("jobs.id", ondelete="CASCADE"),
        nullable=False,
    )
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    payload = _json_col(nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    job: Mapped[Job] = relationship(back_populates="events")

    __table_args__ = (Index("idx_events_job_id", "job_id", "id"),)
