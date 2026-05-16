"""Regression test for the degraded-flag propagation fix.

Previously tool_executor only set `degraded=True` for `budget_exceeded`.
Timeouts, network errors and circuit-open responses left the report
looking complete. We now degrade on any non-ok tool status.
"""

from __future__ import annotations

import pytest

from app.agent.nodes import tool_executor
from app.llm.budget import JobBudget
from app.tools.base import Tool, ToolResult


class _FakeFailingTool(Tool):
    name = "market_data"
    upstream = None

    def __init__(self, status: str) -> None:
        self._status = status

    def schema(self) -> dict:
        return {"name": self.name, "parameters": {}}

    async def _run(self, **kwargs):  # pragma: no cover - bypassed by invoke override
        return {}

    async def invoke(self, budget, **kwargs):  # type: ignore[override]
        return ToolResult(None, status=self._status, error="forced")


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["timeout", "error", "circuit_open"])
async def test_non_ok_tool_status_marks_state_degraded(status):
    budget = JobBudget(max_tool_calls=10, max_tokens=10_000)
    state = {
        "job_id": "test-job",
        "ticker": "TSLA",
        "tool_results": {},
        "tools_used_order": [],
        "tool_invocation_logs": [],
        "citation_urls": [],
        "errors": [],
        "next_tools": ["market_data"],
        "degraded": False,
    }
    tools = {"market_data": _FakeFailingTool(status)}
    out = await tool_executor.run(state, tools, budget)
    assert out["degraded"] is True
    assert out["degradation_reason"]
    assert status.upper() in out["degradation_reason"].upper()
