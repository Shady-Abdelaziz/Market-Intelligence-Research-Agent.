"""LangGraph state machine wiring.

A simple linear-with-loop graph:
    START -> ticker_extractor -> planner -> tool_executor -> reflection_critic
       -> (replan?) -> planner (loop) | -> synthesizer -> END
"""

from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from app.agent.edges import after_reflection, after_ticker_extractor
from app.agent.nodes import planner as planner_node
from app.agent.nodes import reflection_critic as reflection_node
from app.agent.nodes import synthesizer as synth_node
from app.agent.nodes import ticker_extractor as ticker_node
from app.agent.nodes import tool_executor as tool_node
from app.agent.state import AgentState
from app.llm.budget import JobBudget
from app.llm.client import LLMClient
from app.tools.base import Tool
from app.tools.correlation import CorrelationTool
from app.tools.edgar import EdgarTool
from app.tools.market_data import MarketDataTool
from app.tools.news_sentiment import NewsSentimentTool
from app.tools.peer_fundamentals import PeerFundamentalsTool


def build_tools(llm_factory) -> dict[str, Tool]:
    return {
        "market_data": MarketDataTool(),
        "news_sentiment": NewsSentimentTool(llm_factory=llm_factory),
        "correlation": CorrelationTool(),
        "peer_fundamentals": PeerFundamentalsTool(),
        "edgar_filings": EdgarTool(),
    }


def build_graph(llm_factory, tools_by_name: dict[str, Tool], budget: JobBudget):
    graph = StateGraph(AgentState)

    async def n_ticker(state: AgentState) -> AgentState:
        return await ticker_node.run(state, llm_factory)

    async def n_plan(state: AgentState) -> AgentState:
        return await planner_node.run(state, llm_factory)

    async def n_tools(state: AgentState) -> AgentState:
        return await tool_node.run(state, tools_by_name, budget)

    async def n_reflect(state: AgentState) -> AgentState:
        return await reflection_node.run(state)

    async def n_synth(state: AgentState) -> AgentState:
        return await synth_node.run(state, llm_factory, budget)

    graph.add_node("ticker_extractor", n_ticker)
    graph.add_node("planner", n_plan)
    graph.add_node("tool_executor", n_tools)
    graph.add_node("reflection_critic", n_reflect)
    graph.add_node("synthesizer", n_synth)

    graph.add_edge(START, "ticker_extractor")
    graph.add_conditional_edges(
        "ticker_extractor",
        after_ticker_extractor,
        {"planner": "planner", "synthesizer": "synthesizer"},
    )
    graph.add_edge("planner", "tool_executor")
    graph.add_edge("tool_executor", "reflection_critic")
    graph.add_conditional_edges(
        "reflection_critic",
        after_reflection,
        {"planner": "planner", "synthesizer": "synthesizer"},
    )
    graph.add_edge("synthesizer", END)
    return graph.compile()


def llm_factory_default(budget: JobBudget) -> LLMClient:
    return LLMClient(budget)
