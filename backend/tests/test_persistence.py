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
async def test_mark_failed_persists_error(session):
    repo = JobRepo(session)
    job = await repo.create("q")
    await session.commit()
    await repo.mark_failed(job.id, "boom: upstream timeout")
    await session.commit()
    # expire_on_commit=False keeps the original ORM row cached, so re-read
    # via a fresh SELECT against a column to confirm the UPDATE landed.
    from sqlalchemy import select

    from app.persistence.models import Job

    row = (
        await session.execute(
            select(Job.status, Job.error, Job.completed_at).where(Job.id == job.id)
        )
    ).one()
    assert row.status == "failed"
    assert row.error == "boom: upstream timeout"
    assert row.completed_at is not None


@pytest.mark.asyncio
async def test_merge_seen_urls_atomic_preserves_order_and_caps(session):
    repo = MonitorRepo(session)
    t = await repo.upsert("AAPL", 3600, ["MSFT"])
    await session.commit()
    # First batch.
    merged = await repo.merge_seen_urls_and_update_baselines(
        target_id=t.id,
        new_url_hashes=["a", "b", "c"],
        baseline_price_mean=100.0,
        baseline_price_std=1.0,
        baseline_volume_avg=1_000_000.0,
        cap=5,
    )
    await session.commit()
    assert merged == ["a", "b", "c"]
    # Second batch with overlap — dedupe + preserve order.
    merged = await repo.merge_seen_urls_and_update_baselines(
        target_id=t.id,
        new_url_hashes=["b", "d", "e", "f"],
        baseline_price_mean=101.0,
        baseline_price_std=1.5,
        baseline_volume_avg=1_100_000.0,
        cap=5,
    )
    await session.commit()
    # Cap=5 keeps the most-recent 5 of {a,b,c,d,e,f} preserving order.
    assert merged == ["b", "c", "d", "e", "f"]
    fresh = await repo.get_by_id(t.id)
    assert list(fresh.last_seen_article_urls) == ["b", "c", "d", "e", "f"]
    assert float(fresh.baseline_price_mean) == 101.0


@pytest.mark.asyncio
async def test_merge_seen_urls_concurrent_preserves_union(engine):
    """Regression for C5: two concurrent monitor ticks against the same
    target must not clobber each other's URL history. The per-target
    asyncio.Lock + atomic merge guarantee the union is preserved."""
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with factory() as s:
        m = await MonitorRepo(s).upsert("CONC", 3600, [])
        await s.commit()
        tid = str(m.id)

    async def go(urls: list[str]) -> list[str]:
        async with factory() as s:
            return await MonitorRepo(s).merge_seen_urls_and_update_baselines(
                target_id=tid,
                new_url_hashes=urls,
                baseline_price_mean=100.0,
                baseline_price_std=1.0,
                baseline_volume_avg=1.0,
                cap=10,
            )

    import asyncio as _asyncio

    await _asyncio.gather(go(["x1", "x2", "x3"]), go(["x2", "x4", "x5"]))

    async with factory() as s:
        fresh = await MonitorRepo(s).get_by_id(tid)

    final = list(fresh.last_seen_article_urls)
    assert set(final) == {"x1", "x2", "x3", "x4", "x5"}
    assert len(final) == 5  # dedupe held


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
