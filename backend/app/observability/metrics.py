"""Prometheus metrics exposed at /metrics.

Names match Section 13 of the build plan exactly.
"""

from __future__ import annotations

from prometheus_client import Counter, Gauge, Histogram

jobs_total = Counter(
    "mira_jobs_total",
    "Total analysis jobs by terminal status",
    ["status"],
)
job_duration_seconds = Histogram(
    "mira_job_duration_seconds",
    "End-to-end duration of analysis jobs",
    buckets=(1, 5, 10, 30, 60, 120, 300, 600),
)
tool_call_total = Counter(
    "mira_tool_call_total",
    "Per-tool invocation count by status",
    ["tool", "status"],
)
tool_call_latency_seconds = Histogram(
    "mira_tool_call_latency_seconds",
    "Per-tool latency",
    ["tool"],
    buckets=(0.05, 0.1, 0.5, 1, 2, 5, 10, 30),
)
llm_tokens_total = Counter(
    "mira_llm_tokens_total",
    "LLM tokens used",
    ["model", "type"],
)
llm_cost_usd_total = Counter(
    "mira_llm_cost_usd_total",
    "LLM cost in USD",
    ["model"],
)
llm_call_latency_seconds = Histogram(
    "mira_llm_call_latency_seconds",
    "LLM call latency",
    ["model"],
)
reflection_passes = Histogram(
    "mira_reflection_passes",
    "Reflection passes per job",
    buckets=(0, 1, 2, 3, 4),
)
monitor_triggers_total = Counter(
    "mira_monitor_triggers_total",
    "Monitoring trigger fires",
    ["trigger"],
)
monitor_ticks_total = Counter(
    "mira_monitor_ticks_total",
    "Monitor tick outcomes",
    ["status"],
)
circuit_breaker_state = Gauge(
    "mira_circuit_breaker_state",
    "Circuit breaker state: 0=closed, 1=open, 2=halfopen",
    ["upstream"],
)
cache_hits_total = Counter("mira_cache_hits_total", "Cache hits", ["cache"])
cache_misses_total = Counter("mira_cache_misses_total", "Cache misses", ["cache"])
sse_dropped_events_total = Counter(
    "mira_sse_dropped_events_total",
    "In-process SSE events that were dropped due to subscriber backpressure",
)
