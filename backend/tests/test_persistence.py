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
    a = await repo.upsert("AAPL", 60, ["MSFT"])
    b = await repo.upsert("AAPL", 60, ["MSFT"])
    assert a.id == b.id


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
