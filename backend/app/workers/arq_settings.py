"""arq WorkerSettings — queue + cron."""

from __future__ import annotations

from arq.connections import RedisSettings

from app.config import get_settings
from app.observability.logging import configure_logging
from app.workers.jobs import analyze_ticker, monitor_tick

configure_logging()
_settings = get_settings()


def _redis_settings() -> RedisSettings | None:
    if not _settings.redis_enabled:
        return None
    return RedisSettings.from_dsn(_settings.redis_url)


async def on_startup(ctx: dict) -> None:
    from app.cache.redis_cache import init_cache
    from app.resilience.http_client import init_client

    init_client()
    await init_cache()


async def on_shutdown(ctx: dict) -> None:
    from app.cache.redis_cache import close_cache
    from app.resilience.http_client import close_client

    await close_cache()
    await close_client()


class WorkerSettings:
    functions = [analyze_ticker, monitor_tick]
    # No static cron jobs — each monitor_tick self-enqueues the next tick
    # via _defer_by (see jobs._reschedule_monitor_tick), keyed off the
    # target's cadence_seconds.
    cron_jobs = []
    redis_settings = _redis_settings()
    queue_name = "mira_jobs"
    max_jobs = 4
    job_timeout = 600
    keep_result = 3600
    on_startup = on_startup
    on_shutdown = on_shutdown
