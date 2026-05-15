"""Ops endpoints: /health, /ready, /metrics."""

from __future__ import annotations

from fastapi import APIRouter, Request, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from sqlalchemy import text

from app.persistence.db import get_session

router = APIRouter(tags=["ops"])


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/ready")
async def ready(request: Request) -> Response:
    diagnostics: dict[str, str] = {}

    # DB
    try:
        async with get_session() as session:
            await session.execute(text("SELECT 1"))
        diagnostics["database"] = "ok"
    except Exception as e:  # noqa: BLE001
        diagnostics["database"] = f"error:{e}"

    # Redis (if configured)
    pool = request.app.state.arq_pool
    if pool is not None:
        try:
            await pool.ping()
            diagnostics["redis"] = "ok"
        except Exception as e:  # noqa: BLE001
            diagnostics["redis"] = f"error:{e}"
    else:
        diagnostics["redis"] = "disabled"

    ok = all(v == "ok" or v == "disabled" for v in diagnostics.values())
    return Response(
        content=str(diagnostics),
        status_code=200 if ok else 503,
        media_type="application/json",
    )


@router.get("/metrics")
async def metrics() -> Response:
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
