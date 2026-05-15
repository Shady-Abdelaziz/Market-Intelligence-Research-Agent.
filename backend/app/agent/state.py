"""LangGraph state shape carried through every node."""

from __future__ import annotations

from typing import Any, TypedDict


class AgentState(TypedDict, total=False):
    # Inputs
    job_id: str
    query: str

    # Resolved
    ticker: str | None
    company_name: str | None
    sector: str | None
    sector_etf: str | None
    peers: list[str]

    # Tool execution
    plan: str
    next_tools: list[str]
    tool_results: dict[str, Any]
    tool_calls_made: int
    tools_used_order: list[str]
    citation_urls: list[str]
    tool_invocation_logs: list[dict[str, Any]]

    # Reflection
    reflection_passes: int
    triggers_fired: list[str]
    needs_replan: bool
    reflection_thoughts: list[dict[str, Any]]

    # Budget
    tokens_used: int
    cost_usd: float

    # Errors
    errors: list[str]
    degraded: bool
    degradation_reason: str | None

    # Output
    report: dict[str, Any] | None
