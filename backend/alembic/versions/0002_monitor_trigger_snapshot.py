"""add Job.monitor_trigger_snapshot

Captures the value-at-fire-time of the three monitoring triggers
(new_articles count, price σ deviation, volume ×ratio) so the UI can
show real numbers on alert rows instead of mixing "current σ" with
"historical fire status".

Revision ID: 0002_monitor_trigger_snapshot
Revises: 0001_initial
Create Date: 2026-05-16
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0002_monitor_trigger_snapshot"
down_revision: str | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    is_pg = bind.dialect.name == "postgresql"
    json_type = postgresql.JSONB() if is_pg else sa.JSON()
    op.add_column(
        "jobs",
        sa.Column("monitor_trigger_snapshot", json_type, nullable=True),
    )


def downgrade() -> None:
    op.drop_column("jobs", "monitor_trigger_snapshot")
