"""Structured logging configuration using structlog.

Context vars (request_id, job_id, tool_name) are propagated through the
processor chain so every log line carries job-level context automatically.
"""

from __future__ import annotations

import logging
import sys
from contextvars import ContextVar
from typing import Any

import structlog

from app.config import get_settings

request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)
job_id_var: ContextVar[str | None] = ContextVar("job_id", default=None)
tool_name_var: ContextVar[str | None] = ContextVar("tool_name", default=None)


def _add_context_vars(_logger: Any, _method: str, event_dict: dict[str, Any]) -> dict[str, Any]:
    rid = request_id_var.get()
    jid = job_id_var.get()
    tname = tool_name_var.get()
    if rid:
        event_dict.setdefault("request_id", rid)
    if jid:
        event_dict.setdefault("job_id", jid)
    if tname:
        event_dict.setdefault("tool", tname)
    return event_dict


def configure_logging() -> None:
    settings = get_settings()

    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
    )

    processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        _add_context_vars,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    if settings.log_format == "json":
        processors.append(structlog.processors.JSONRenderer())
    else:
        processors.append(structlog.dev.ConsoleRenderer())

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.stdlib.BoundLogger,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    return structlog.get_logger(name)
