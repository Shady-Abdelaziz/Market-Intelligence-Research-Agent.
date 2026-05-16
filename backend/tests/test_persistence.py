from __future__ import annotations

import pytest

from app.persistence.repos import JobRepo, MonitorRepo, ToolLogRepo


@pytest.mark.asyncio
async def test_job_lifecycle(session):
    repo = JobRepo(session)
    job = await repo.create("test query", ticker="TSLA")
    await session.commit()

    await repo.mark_running(job.id)
    await session.commit()
    fetched = await repo.get(job.id)
    assert fetched.status == "running"

    await repo.mark_completed(
        job_id=job.id,
        result_json={"ok": True},
        prompt_tokens=10,
        completion_tokens=20,
        cost_usd=0.0001,
        tool_calls_count=3,
        reflection_passes=1,
        triggers_fired=["stale_news"],
    )
    await session.commit()
    fetched = await repo.get(job.id)
    assert fetched.status == "completed"
    assert fetched.tool_calls_count == 3


@pytest.mark.asyncio
async def test_monitor_upsert_idempotent(session):
    repo = MonitorRepo(session)
    a = await repo.upsert("AAPL", 3600, ["MSFT"])
    b = await repo.upsert("AAPL", 3600, ["MSFT"])
    assert a.id == b.id


@pytest.mark.asyncio
async def test_monitor_upsert_resets_article_history(session):
    """Re-adding a monitor is "fresh start" semantics. Stale article hashes
    from a previous registration would falsely suppress the first
    `articles` trigger; a stale baselines_computed_at would mask the
    age of the baselines we're about to overwrite."""
    repo = MonitorRepo(session)
    t = await repo.upsert("MSFT", 3600, ["AAPL"])
    # Simulate accumulated state from a prior live monitor.
    t.last_seen_article_urls = ["hash_a", "hash_b", "hash_c"]
    from datetime import UTC, datetime

    t.baselines_computed_at = datetime.now(UTC)
    await session.flush()

    # Re-upsert (e.g. user clicks "Add" again after a Stop).
    t2 = await repo.upsert("MSFT", 7200, ["GOOGL"])
    assert t.id == t2.id
    assert t2.last_seen_article_urls == []
    assert t2.baselines_computed_at is None
    assert t2.cadence_seconds == 7200
    assert t2.peers == ["GOOGL"]


@pytest.mark.asyncio
async def test_reset_running_to_interrupted(session):
    repo = JobRepo(session)
    job = await repo.create("q")
    await repo.mark_running(job.id)
    await session.commit()
    n = await repo.reset_running_to_interrupted()
    await session.commit()
    assert n >= 1
    fetched = await repo.get(job.id)
    assert fetched.status == "interrupted"


@pytest.mark.asyncio
async def test_tool_log(session):
    job = await JobRepo(session).create("q")
    await session.commit()
    await ToolLogRepo(session).log(
        job.id, "market_data", {"ticker": "TSLA"}, "TSLA @ $200", 250, "success"
    )
    await session.commit()
    rows = await ToolLogRepo(session).list_for_job(job.id)
    assert len(rows) == 1
    assert rows[0].tool_name == "market_data"
