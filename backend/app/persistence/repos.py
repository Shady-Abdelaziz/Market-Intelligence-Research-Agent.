"""Repository classes — thin wrappers over SQLAlchemy sessions.

Each repo exposes intent-revealing methods (create_job, mark_completed, etc.)
rather than leaking raw queries to callers.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.persistence.models import (
    AgentEvent,
    Article,
    Job,
    LLMCall,
    MonitoringTarget,
    ToolInvocation,
)


def _now_utc() -> datetime:
    return datetime.now(UTC)


class JobRepo:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, query: str, ticker: str | None = None) -> Job:
        job = Job(query=query, ticker=ticker, status="queued")
        self.session.add(job)
        await self.session.flush()
        return job

    async def get(self, job_id: uuid.UUID | str) -> Job | None:
        return await self.session.get(Job, str(job_id) if isinstance(job_id, uuid.UUID) else job_id)

    async def mark_running(self, job_id: uuid.UUID | str) -> None:
        await self.session.execute(
            update(Job).where(Job.id == job_id).values(status="running", started_at=_now_utc())
        )

    async def mark_completed(
        self,
        job_id: uuid.UUID | str,
        result_json: dict[str, Any],
        prompt_tokens: int,
        completion_tokens: int,
        cost_usd: float,
        tool_calls_count: int,
        reflection_passes: int,
        triggers_fired: list[str],
        alert_tag: str | None = None,
    ) -> None:
        await self.session.execute(
            update(Job)
            .where(Job.id == job_id)
            .values(
                status="completed",
                completed_at=_now_utc(),
                result_json=result_json,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                cost_usd=Decimal(str(cost_usd)),
                tool_calls_count=tool_calls_count,
                reflection_passes=reflection_passes,
                triggers_fired=triggers_fired,
                alert_tag=alert_tag,
            )
        )

    async def mark_failed(self, job_id: uuid.UUID | str, error: str) -> None:
        await self.session.execute(
            update(Job)
            .where(Job.id == job_id)
            .values(status="failed", completed_at=_now_utc(), error=error)
        )

    async def reset_running_to_interrupted(self) -> int:
        """On startup: jobs still in 'running' state died with the previous container."""
        result = await self.session.execute(
            update(Job).where(Job.status == "running").values(status="interrupted")
        )
        return result.rowcount or 0


class MonitorRepo:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def upsert(
        self,
        ticker: str,
        cadence_seconds: int,
        peers: list[str],
    ) -> MonitoringTarget:
        existing = await self.session.execute(
            select(MonitoringTarget).where(MonitoringTarget.ticker == ticker)
        )
        target = existing.scalar_one_or_none()
        if target:
            target.cadence_seconds = cadence_seconds
            target.peers = peers
            target.active = True
            # Re-adding a monitor is "fresh start" semantics: any in-flight
            # article history and the stale baseline timestamp from the
            # previous registration would falsely suppress the first
            # `articles` trigger or mask staleness. Numeric baselines get
            # rewritten by the caller (monitor_start) or the next tick.
            target.last_seen_article_urls = []
            target.baselines_computed_at = None
        else:
            target = MonitoringTarget(
                ticker=ticker,
                cadence_seconds=cadence_seconds,
                peers=peers,
            )
            self.session.add(target)
        await self.session.flush()
        return target

    async def get_by_ticker(self, ticker: str) -> MonitoringTarget | None:
        result = await self.session.execute(
            select(MonitoringTarget).where(MonitoringTarget.ticker == ticker)
        )
        return result.scalar_one_or_none()

    async def get_by_id(self, target_id: uuid.UUID | str) -> MonitoringTarget | None:
        return await self.session.get(MonitoringTarget, str(target_id))

    async def list_active(self) -> list[MonitoringTarget]:
        result = await self.session.execute(
            select(MonitoringTarget).where(MonitoringTarget.active.is_(True))
        )
        return list(result.scalars().all())

    async def update_baselines_and_run(
        self,
        target_id: uuid.UUID | str,
        baseline_price_mean: float,
        baseline_price_std: float,
        baseline_volume_avg: float,
        last_seen_article_urls: list[str],
    ) -> None:
        await self.session.execute(
            update(MonitoringTarget)
            .where(MonitoringTarget.id == target_id)
            .values(
                baseline_price_mean=Decimal(str(baseline_price_mean)),
                baseline_price_std=Decimal(str(baseline_price_std)),
                baseline_volume_avg=Decimal(str(baseline_volume_avg)),
                baselines_computed_at=_now_utc(),
                last_run_at=_now_utc(),
                last_seen_article_urls=last_seen_article_urls,
            )
        )

    async def deactivate(self, ticker: str) -> bool:
        result = await self.session.execute(
            update(MonitoringTarget).where(MonitoringTarget.ticker == ticker).values(active=False)
        )
        return (result.rowcount or 0) > 0

    async def history(self, ticker: str, limit: int = 50) -> list[Job]:
        target = await self.get_by_ticker(ticker)
        if not target:
            return []
        result = await self.session.execute(
            select(Job)
            .where(Job.monitor_target_id == target.id, Job.alert_tag == "PROACTIVE_ALERT")
            .order_by(Job.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())


class ToolLogRepo:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def log(
        self,
        job_id: uuid.UUID | str,
        tool_name: str,
        input_data: dict[str, Any],
        output_summary: str | None,
        latency_ms: int,
        status: str,
        error: str | None = None,
    ) -> None:
        self.session.add(
            ToolInvocation(
                job_id=job_id,
                tool_name=tool_name,
                input_json=input_data,
                output_summary=output_summary,
                latency_ms=latency_ms,
                status=status,
                error=error,
            )
        )
        await self.session.flush()

    async def list_for_job(self, job_id: uuid.UUID | str) -> list[ToolInvocation]:
        result = await self.session.execute(
            select(ToolInvocation)
            .where(ToolInvocation.job_id == job_id)
            .order_by(ToolInvocation.created_at)
        )
        return list(result.scalars().all())


class LLMCallRepo:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def log(
        self,
        job_id: uuid.UUID | str,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
        cost_usd: float,
        latency_ms: int,
        cached: bool = False,
    ) -> None:
        self.session.add(
            LLMCall(
                job_id=job_id,
                model=model,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                cost_usd=Decimal(str(cost_usd)),
                latency_ms=latency_ms,
                cached=cached,
            )
        )
        await self.session.flush()


class ArticleRepo:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def upsert(
        self,
        url_hash: str,
        url: str,
        title: str | None,
        title_fingerprint: str | None,
        source: str | None,
        published_at: datetime | None,
        ticker: str | None,
        raw_json: dict[str, Any],
        sentiment_label: str | None = None,
        sentiment_score: float | None = None,
        cached_until: datetime | None = None,
    ) -> None:
        existing = await self.session.get(Article, url_hash)
        if existing:
            existing.sentiment_label = sentiment_label or existing.sentiment_label
            if sentiment_score is not None:
                existing.sentiment_score = Decimal(str(sentiment_score))
            existing.cached_until = cached_until or existing.cached_until
            return
        self.session.add(
            Article(
                url_hash=url_hash,
                url=url,
                title=title,
                title_fingerprint=title_fingerprint,
                source=source,
                published_at=published_at,
                ticker=ticker,
                raw_json=raw_json,
                sentiment_label=sentiment_label,
                sentiment_score=Decimal(str(sentiment_score))
                if sentiment_score is not None
                else None,
                cached_until=cached_until,
            )
        )
        await self.session.flush()


class EventRepo:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def append(
        self,
        job_id: uuid.UUID | str,
        event_type: str,
        payload: dict[str, Any],
    ) -> AgentEvent:
        ev = AgentEvent(job_id=job_id, event_type=event_type, payload=payload)
        self.session.add(ev)
        await self.session.flush()
        return ev

    async def list_since(
        self, job_id: uuid.UUID | str, last_id: int | None = None
    ) -> list[AgentEvent]:
        query = select(AgentEvent).where(AgentEvent.job_id == job_id)
        if last_id is not None:
            query = query.where(AgentEvent.id > last_id)
        query = query.order_by(AgentEvent.id)
        result = await self.session.execute(query)
        return list(result.scalars().all())
