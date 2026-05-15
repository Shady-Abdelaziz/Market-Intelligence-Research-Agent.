"""Tool base class wrapping every external call with logging, latency,
budget enforcement, and circuit-breaker checks.

Each tool subclass defines:
- name: stable identifier (used in tools_used[] and logs)
- upstream: which circuit breaker to consult
- schema(): OpenAI function-calling schema
- _run(): the actual work (async)

The decorator-style `Tool.invoke()` method handles all the cross-cutting
concerns so subclasses stay focused on the API call.
"""

from __future__ import annotations

import abc
import time
from typing import Any

from app.llm.budget import BudgetExceeded, JobBudget
from app.observability.logging import get_logger, tool_name_var
from app.observability.metrics import tool_call_latency_seconds, tool_call_total
from app.resilience.breakers import CircuitOpenError, breakers

log = get_logger(__name__)


class ToolResult:
    """Wraps tool output with a status that the agent can branch on."""

    def __init__(
        self,
        data: dict[str, Any] | None,
        status: str = "success",
        error: str | None = None,
        summary: str = "",
        latency_ms: int = 0,
    ):
        self.data = data
        self.status = status
        self.error = error
        self.summary = summary
        self.latency_ms = latency_ms

    @property
    def ok(self) -> bool:
        return self.status == "success"

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "data": self.data,
            "error": self.error,
            "summary": self.summary,
            "latency_ms": self.latency_ms,
        }


class Tool(abc.ABC):
    name: str = "tool"
    upstream: str | None = None  # which breaker, None = no breaker

    @abc.abstractmethod
    def schema(self) -> dict[str, Any]:
        """OpenAI function-calling schema for this tool."""

    @abc.abstractmethod
    async def _run(self, **kwargs: Any) -> dict[str, Any]:
        """Actual implementation — return a dict (will be wrapped in ToolResult)."""

    def summarize(self, output: dict[str, Any]) -> str:
        """Short human-readable summary for logging. Override per-tool."""
        return "ok"

    async def invoke(self, budget: JobBudget, **kwargs: Any) -> ToolResult:
        token = tool_name_var.set(self.name)
        t0 = time.monotonic()
        try:
            budget.check_tool_call()
        except BudgetExceeded as e:
            tool_call_total.labels(tool=self.name, status="budget_exceeded").inc()
            tool_name_var.reset(token)
            return ToolResult(None, status="budget_exceeded", error=e.reason)

        if self.upstream and breakers[self.upstream].current_state == "open":
            tool_call_total.labels(tool=self.name, status="circuit_open").inc()
            tool_name_var.reset(token)
            return ToolResult(None, status="circuit_open", error=f"circuit_open:{self.upstream}")

        try:
            data = await self._run(**kwargs)
            latency_ms = int((time.monotonic() - t0) * 1000)
            budget.record_tool_call()
            tool_call_total.labels(tool=self.name, status="success").inc()
            tool_call_latency_seconds.labels(tool=self.name).observe(latency_ms / 1000)
            log.info("tool_ok", tool=self.name, latency_ms=latency_ms)
            return ToolResult(data, "success", None, self.summarize(data), latency_ms)
        except CircuitOpenError as e:
            latency_ms = int((time.monotonic() - t0) * 1000)
            tool_call_total.labels(tool=self.name, status="circuit_open").inc()
            log.warning("tool_circuit_open", tool=self.name, error=str(e))
            return ToolResult(None, "circuit_open", str(e), "", latency_ms)
        except Exception as e:  # noqa: BLE001
            latency_ms = int((time.monotonic() - t0) * 1000)
            tool_call_total.labels(tool=self.name, status="error").inc()
            log.error("tool_error", tool=self.name, error=str(e), latency_ms=latency_ms)
            return ToolResult(None, "error", str(e), "", latency_ms)
        finally:
            tool_name_var.reset(token)
