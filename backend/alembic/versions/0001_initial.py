"""initial schema

Revision ID: 0001_initial
Revises:
Create Date: 2026-05-15

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    is_pg = bind.dialect.name == "postgresql"

    uuid_type = postgresql.UUID(as_uuid=True) if is_pg else sa.String(36)
    json_type = postgresql.JSONB() if is_pg else sa.JSON()
    text_array = postgresql.ARRAY(sa.Text) if is_pg else sa.JSON()

    op.create_table(
        "monitoring_targets",
        sa.Column("id", uuid_type, primary_key=True),
        sa.Column("ticker", sa.String(16), nullable=False, unique=True),
        sa.Column("cadence_seconds", sa.Integer, nullable=False, server_default="86400"),
        sa.Column("peers", text_array, nullable=False, server_default=sa.text("'{}'" if is_pg else "'[]'")),
        sa.Column("baseline_price_mean", sa.Numeric(14, 4), nullable=True),
        sa.Column("baseline_price_std", sa.Numeric(14, 4), nullable=True),
        sa.Column("baseline_volume_avg", sa.Numeric(20, 2), nullable=True),
        sa.Column("baselines_computed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "last_seen_article_urls",
            text_array,
            nullable=False,
            server_default=sa.text("'{}'" if is_pg else "'[]'"),
        ),
        sa.Column("active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "jobs",
        sa.Column("id", uuid_type, primary_key=True),
        sa.Column("query", sa.Text, nullable=False),
        sa.Column("ticker", sa.String(16), nullable=True),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("result_json", json_type, nullable=True),
        sa.Column("error", sa.Text, nullable=True),
        sa.Column("prompt_tokens", sa.Integer, server_default="0"),
        sa.Column("completion_tokens", sa.Integer, server_default="0"),
        sa.Column("cost_usd", sa.Numeric(10, 6), server_default="0"),
        sa.Column("tool_calls_count", sa.Integer, server_default="0"),
        sa.Column("reflection_passes", sa.Integer, server_default="0"),
        sa.Column("alert_tag", sa.String(32), nullable=True),
        sa.Column(
            "monitor_target_id",
            uuid_type,
            sa.ForeignKey("monitoring_targets.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "triggers_fired",
            text_array,
            nullable=False,
            server_default=sa.text("'{}'" if is_pg else "'[]'"),
        ),
    )
    op.create_index("idx_jobs_status", "jobs", ["status"])
    op.create_index("idx_jobs_ticker", "jobs", ["ticker"])
    op.create_index("idx_jobs_created", "jobs", ["created_at"])

    op.create_table(
        "tool_invocations",
        sa.Column("id", uuid_type, primary_key=True),
        sa.Column(
            "job_id",
            uuid_type,
            sa.ForeignKey("jobs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("tool_name", sa.String(64), nullable=False),
        sa.Column("input_json", json_type, nullable=False),
        sa.Column("output_summary", sa.Text, nullable=True),
        sa.Column("latency_ms", sa.Integer, nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("error", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("idx_tool_inv_job", "tool_invocations", ["job_id"])

    op.create_table(
        "llm_calls",
        sa.Column("id", uuid_type, primary_key=True),
        sa.Column(
            "job_id",
            uuid_type,
            sa.ForeignKey("jobs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("model", sa.String(128), nullable=False),
        sa.Column("prompt_tokens", sa.Integer, nullable=False),
        sa.Column("completion_tokens", sa.Integer, nullable=False),
        sa.Column("cost_usd", sa.Numeric(10, 6), nullable=False),
        sa.Column("latency_ms", sa.Integer, nullable=False),
        sa.Column("cached", sa.Boolean, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("idx_llm_calls_job", "llm_calls", ["job_id"])

    op.create_table(
        "articles",
        sa.Column("url_hash", sa.String(64), primary_key=True),
        sa.Column("url", sa.Text, nullable=False),
        sa.Column("title", sa.Text, nullable=True),
        sa.Column("title_fingerprint", sa.String(64), nullable=True),
        sa.Column("source", sa.String(255), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ticker", sa.String(16), nullable=True),
        sa.Column("raw_json", json_type, nullable=True),
        sa.Column("sentiment_label", sa.String(16), nullable=True),
        sa.Column("sentiment_score", sa.Numeric(5, 4), nullable=True),
        sa.Column("cached_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("idx_articles_ticker_pub", "articles", ["ticker", "published_at"])

    op.create_table(
        "agent_events",
        # Integer for SQLite (so it becomes ROWID-style autoincrement),
        # BigInteger on Postgres via the conditional below.
        sa.Column(
            "id",
            sa.Integer().with_variant(sa.BigInteger(), "postgresql"),
            primary_key=True,
            autoincrement=True,
        ),
        sa.Column(
            "job_id",
            uuid_type,
            sa.ForeignKey("jobs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("payload", json_type, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("idx_events_job_id", "agent_events", ["job_id", "id"])


def downgrade() -> None:
    op.drop_table("agent_events")
    op.drop_table("articles")
    op.drop_table("llm_calls")
    op.drop_table("tool_invocations")
    op.drop_table("jobs")
    op.drop_table("monitoring_targets")
