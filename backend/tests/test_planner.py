"""Planner regression tests — first-pass LLM-driven plan + reflection triggers."""

from __future__ import annotations

from app.agent.nodes import planner
from app.llm.budget import JobBudget


class _FakeMessage:
    def __init__(self, content: str):
        self.content = content


class _FakeChoice:
    def __init__(self, content: str):
        self.message = _FakeMessage(content)


class _FakeResp:
    def __init__(self, content: str):
        self.choices = [_FakeChoice(content)]


class _FakeLLM:
    """Records prompts and returns canned JSON. Lets us assert the planner
    actually consults the LLM (rather than the old hardcoded first-pass
    behaviour)."""

    def __init__(self, content: str):
        self._content = content
        self.calls: list[dict] = []

    async def chat(self, messages, **kwargs):
        self.calls.append({"messages": messages, **kwargs})
        return _FakeResp(self._content)


def _factory(llm: _FakeLLM):
    def _f(_budget):
        return llm

    return _f


async def _run_planner(state, llm_content: str):
    llm = _FakeLLM(llm_content)
    factory = _factory(llm)
    budget = JobBudget(max_tool_calls=10, max_tokens=1_000_000)
    out = await planner.run(state, factory, budget)
    return out, llm


async def test_initial_plan_consults_the_llm_with_the_query():
    """Brief §2B: the agent must use its planning ability to decide which
    tool to invoke next *based on the input query*. First pass must call
    the LLM."""
    state = {
        "job_id": "j1",
        "query": "Should I worry about AAPL margin compression?",
        "ticker": "AAPL",
        "company_name": "Apple Inc.",
        "triggers_fired": [],
        "reflection_passes": 0,
        "tool_results": {},
        "tools_used_order": [],
    }
    out, llm = await _run_planner(
        state,
        '{"plan": "AAPL margin focus", "tools": ["market_data", "news_sentiment", "edgar_filings"]}',
    )
    assert len(llm.calls) == 1, "planner must consult the LLM on the first pass"
    user_msg = next(m for m in llm.calls[0]["messages"] if m["role"] == "user")
    assert "AAPL margin compression" in user_msg["content"]
    assert "initial" in user_msg["content"]
    assert out["next_tools"][0] == "market_data"
    assert "edgar_filings" in out["next_tools"]


async def test_initial_plan_falls_back_to_three_tools_when_llm_returns_nothing():
    """If the LLM is unreachable / returns junk, we still ship a useful
    first pass — never block."""
    state = {
        "job_id": "j2",
        "query": "Analyze MSFT",
        "ticker": "MSFT",
        "company_name": "Microsoft",
        "triggers_fired": [],
        "reflection_passes": 0,
        "tool_results": {},
        "tools_used_order": [],
    }
    out, _ = await _run_planner(state, "not json")
    assert set(out["next_tools"]) >= {"market_data", "news_sentiment", "correlation"}


async def test_initial_plan_unions_llm_choice_with_three_core_tools():
    """Brief §2B mandates at least three distinct tools. If the LLM returns
    a strict subset (e.g. just market_data), the planner must STILL plan
    news_sentiment + correlation alongside it — not silently honor a
    one-tool plan."""
    state = {
        "job_id": "j-union",
        "query": "Quick price check on AAPL",
        "ticker": "AAPL",
        "company_name": "Apple Inc.",
        "triggers_fired": [],
        "reflection_passes": 0,
        "tool_results": {},
        "tools_used_order": [],
    }
    out, _ = await _run_planner(
        state, '{"plan": "just price", "tools": ["market_data"]}'
    )
    assert set(out["next_tools"]) >= {"market_data", "news_sentiment", "correlation"}
    # LLM's choice keeps its leading position; the union appends missing
    # core tools in declaration order after the LLM's picks.
    assert out["next_tools"][0] == "market_data"


async def test_sector_correlation_trigger_adds_peer_news_and_peer_fundamentals():
    """Brief §3A trigger 1 demands a direct competitor's recent news AND
    price action. Peer price action is already in correlation.vs_peers;
    this asserts the planner also enqueues peer_news on reflection."""
    state = {
        "job_id": "j3",
        "query": "Analyze KO",
        "ticker": "KO",
        "company_name": "Coca-Cola",
        "peers": ["PEP", "MNST"],
        "triggers_fired": ["sector_correlation"],
        "reflection_passes": 1,
        "tool_results": {
            "correlation": {"vs_sector_etf": 0.97, "sector_etf_symbol": "XLP"},
        },
        "tools_used_order": ["market_data", "news_sentiment", "correlation"],
    }
    out, _ = await _run_planner(state, '{"plan": "follow up on peers", "tools": []}')
    assert "peer_news" in out["next_tools"], "peer_news must be enqueued on sector_correlation"
    assert "peer_fundamentals" in out["next_tools"]


async def test_stale_news_or_neutral_sentiment_trigger_adds_edgar():
    state = {
        "job_id": "j4",
        "query": "Analyze TSLA",
        "ticker": "TSLA",
        "company_name": "Tesla",
        "peers": ["F", "GM"],
        "triggers_fired": ["neutral_sentiment"],
        "reflection_passes": 1,
        "tool_results": {},
        "tools_used_order": ["market_data", "news_sentiment", "correlation"],
    }
    out, _ = await _run_planner(state, '{"plan": "fetch filings", "tools": []}')
    assert "edgar_filings" in out["next_tools"]
