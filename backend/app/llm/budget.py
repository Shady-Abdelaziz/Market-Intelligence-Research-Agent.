"""Per-job token + cost + tool-call budget enforcement.

The budget is held in a small state object attached to each agent run.
Tools and LLM calls increment counters; exceeding thresholds raises
BudgetExceeded which the agent traps to emit a degraded report.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from app.config import get_settings

_PRICING_PATH = Path(__file__).parent / "pricing.yaml"


def _load_pricing() -> dict[str, Any]:
    with _PRICING_PATH.open() as f:
        return yaml.safe_load(f)


_PRICING = _load_pricing()


class BudgetExceeded(RuntimeError):
    """Raised when a job exceeds its tool-call, token, or cost budget."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


@dataclass
class JobBudget:
    max_tool_calls: int
    max_tokens: int
    tool_calls_made: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cost_usd: float = 0.0
    per_model: dict[str, dict[str, int | float]] = field(default_factory=dict)

    @classmethod
    def from_settings(cls) -> JobBudget:
        s = get_settings()
        return cls(max_tool_calls=s.max_tool_calls, max_tokens=s.max_tokens_per_job)

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens

    def check_tool_call(self) -> None:
        if self.tool_calls_made >= self.max_tool_calls:
            raise BudgetExceeded("TOOL_CALL_BUDGET_EXCEEDED")

    def record_tool_call(self) -> None:
        self.tool_calls_made += 1

    def record_llm_usage(
        self, model: str, prompt_tokens: int, completion_tokens: int, cached: bool = False
    ) -> float:
        self.prompt_tokens += prompt_tokens
        self.completion_tokens += completion_tokens
        cost = estimate_cost(model, prompt_tokens, completion_tokens, cached=cached)
        self.cost_usd += cost
        slot = self.per_model.setdefault(model, {"prompt": 0, "completion": 0, "cost_usd": 0.0})
        slot["prompt"] += prompt_tokens
        slot["completion"] += completion_tokens
        slot["cost_usd"] = float(slot["cost_usd"]) + cost
        if self.total_tokens > self.max_tokens:
            raise BudgetExceeded("TOKEN_BUDGET_EXCEEDED")
        return cost


def estimate_cost(
    model: str, prompt_tokens: int, completion_tokens: int, cached: bool = False
) -> float:
    pricing = _PRICING.get("models", {}).get(model)
    if not pricing:
        pricing = _PRICING.get("default", {"input": 1.0, "output": 3.0})
    input_rate = pricing.get(
        "cached_input" if cached and "cached_input" in pricing else "input", 0.0
    )
    output_rate = pricing.get("output", 0.0)
    return (prompt_tokens * input_rate + completion_tokens * output_rate) / 1_000_000.0
