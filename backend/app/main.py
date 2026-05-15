"""FastAPI application entry point."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from arq import create_pool
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app.api import analyze, monitor, ops, status
from app.cache.redis_cache import close_cache, init_cache
from app.config import get_settings
from app.observability.logging import configure_logging, get_logger, request_id_var
from app.observability.ratelimit import limiter
from app.persistence.db import dispose_engine, get_session
from app.persistence.repos import JobRepo
from app.resilience.http_client import close_client, init_client
from app.workers.arq_settings import _redis_settings

configure_logging()
log = get_logger(__name__)
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    init_client()
    await init_cache()
    # arq pool (optional, falls back to in-process for standalone)
    pool = None
    rs = _redis_settings()
    if rs is not None:
        try:
            pool = await create_pool(rs)
        except Exception as e:  # noqa: BLE001
            log.warning("arq_pool_init_failed", error=str(e))
            pool = None
    app.state.arq_pool = pool

    # On boot: any running job is dead — flip to interrupted
    try:
        async with get_session() as session:
            n = await JobRepo(session).reset_running_to_interrupted()
            if n:
                log.info("reset_running_jobs", count=n)
    except Exception as e:  # noqa: BLE001
        log.warning("startup_reset_failed", error=str(e))

    yield

    if pool is not None:
        await pool.close()
    await close_cache()
    await close_client()
    await dispose_engine()


def create_app() -> FastAPI:
    app = FastAPI(
        title="M.I.R.A. — Market Intelligence & Research Agent",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_handler)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.frontend_origin, "*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(SlowAPIMiddleware)

    @app.middleware("http")
    async def request_id_middleware(request: Request, call_next):
        rid = request.headers.get("x-request-id") or str(uuid.uuid4())
        token = request_id_var.set(rid)
        try:
            response = await call_next(request)
        finally:
            request_id_var.reset(token)
        response.headers["x-request-id"] = rid
        return response

    app.include_router(analyze.router)
    app.include_router(status.router)
    app.include_router(monitor.router)
    app.include_router(ops.router)

    return app


def _rate_limit_handler(request: Request, exc: RateLimitExceeded) -> Response:
    return Response(
        content='{"detail":"rate_limit_exceeded"}',
        status_code=429,
        media_type="application/json",
        headers={"Retry-After": "30"},
    )


app = create_app()
