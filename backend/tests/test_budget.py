from __future__ import annotations

import pytest

from app.llm.budget import BudgetExceeded, JobBudget, estimate_cost


def test_estimate_cost_grok():
    cost = estimate_cost("x-ai/grok-4.3", 1_000_000, 1_000_000)
    assert cost == pytest.approx(1.25 + 2.50, rel=1e-3)


def test_estimate_cost_unknown_uses_default():
    cost = estimate_cost("nonexistent-model", 1_000_000, 0)
    assert cost == pytest.approx(1.0, rel=1e-3)


def test_tool_call_budget_blocks_at_limit():
    b = JobBudget(max_tool_calls=2, max_tokens=1_000_000)
    b.record_tool_call()
    b.record_tool_call()
    with pytest.raises(BudgetExceeded):
        b.check_tool_call()


def test_token_budget_raises_when_exceeded():
    b = JobBudget(max_tool_calls=10, max_tokens=100)
    with pytest.raises(BudgetExceeded):
        b.record_llm_usage("x-ai/grok-4.3", prompt_tokens=80, completion_tokens=50)


def test_per_model_ledger():
    b = JobBudget(max_tool_calls=10, max_tokens=10_000_000)
    b.record_llm_usage("x-ai/grok-4.3", 1000, 500)
    b.record_llm_usage("x-ai/grok-4.3", 200, 100)
    b.record_llm_usage("meta-llama/llama-3.3-70b-instruct:free", 1000, 1000)
    assert b.per_model["x-ai/grok-4.3"]["prompt"] == 1200
    assert b.per_model["x-ai/grok-4.3"]["completion"] == 600
    assert b.per_model["meta-llama/llama-3.3-70b-instruct:free"]["cost_usd"] == 0.0
