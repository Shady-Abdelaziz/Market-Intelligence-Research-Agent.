"""Conditional edge functions."""

from __future__ import annotations

from typing import Literal

from app.agent.state import AgentState
from app.config import get_settings


def after_ticker_extractor(state: AgentState) -> Literal["planner", "synthesizer"]:
    if state.get("ticker"):
        return "planner"
    return "synthesizer"


def after_reflection(state: AgentState) -> Literal["planner", "synthesizer"]:
    s = get_settings()
    if state.get("needs_replan") and state.get("reflection_passes", 0) <= s.max_reflection_passes:
        return "planner"
    return "synthesizer"
