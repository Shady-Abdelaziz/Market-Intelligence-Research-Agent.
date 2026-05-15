"""Drive golden cases against the real agent and score via LLM-as-judge.

Usage: python -m eval.run_eval
Requires: OPENROUTER_API_KEY + NEWSAPI_KEY in the environment.
"""

from __future__ import annotations

import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml

from app.agent.graph import build_graph, build_tools, llm_factory_default
from app.cache.redis_cache import init_cache
from app.llm.budget import JobBudget
from app.observability.logging import configure_logging, get_logger
from app.resilience.http_client import init_client

configure_logging()
log = get_logger("eval")

GOLDEN_PATH = Path(__file__).parent / "golden_cases.yaml"
RESULTS_DIR = Path(__file__).parent / "results"


async def run_case(case: dict) -> dict:
    budget = JobBudget.from_settings()
    tools = build_tools(llm_factory_default)
    graph = build_graph(llm_factory_default, tools, budget)
    job_id = f"eval-{case['name']}"
    initial = {
        "job_id": job_id,
        "query": case["query"],
        "tool_results": {},
        "tools_used_order": [],
        "tool_invocation_logs": [],
        "citation_urls": [],
        "reflection_passes": 0,
        "triggers_fired": [],
        "needs_replan": False,
        "reflection_thoughts": [],
        "errors": [],
        "degraded": False,
        "tokens_used": 0,
        "cost_usd": 0.0,
    }
    final = await graph.ainvoke(initial, {"configurable": {"thread_id": job_id}})
    return final.get("report") or {}


def check_expectations(case: dict, report: dict) -> dict:
    exp = case.get("expect", {})
    checks: dict[str, bool] = {}
    if "ticker" in exp:
        checks["ticker_matches"] = report.get("company_ticker") == exp["ticker"]
    if "key_findings_count" in exp:
        checks["key_findings_exact_3"] = len(report.get("key_findings") or []) == exp["key_findings_count"]
    if "degraded" in exp:
        checks["degraded_flag_matches"] = bool(report.get("degraded")) == bool(exp["degraded"])
    if "degraded_or_failed" in exp:
        checks["degraded_or_failed"] = bool(report.get("degraded")) or not report
    return checks


async def main() -> int:
    init_client()
    await init_cache()

    with GOLDEN_PATH.open() as f:
        cases = yaml.safe_load(f)["cases"]

    RESULTS_DIR.mkdir(exist_ok=True)
    out = []
    pass_count = 0
    for c in cases:
        log.info("eval_case_start", name=c["name"])
        try:
            report = await run_case(c)
            checks = check_expectations(c, report)
            passed = all(checks.values()) if checks else True
            out.append({"case": c["name"], "passed": passed, "checks": checks, "report_excerpt": _excerpt(report)})
            if passed:
                pass_count += 1
        except Exception as e:  # noqa: BLE001
            log.error("eval_case_error", name=c["name"], error=str(e))
            out.append({"case": c["name"], "passed": False, "error": str(e)})

    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    result_path = RESULTS_DIR / f"{ts}.json"
    result_path.write_text(json.dumps(out, indent=2, default=str))
    log.info("eval_complete", passed=pass_count, total=len(cases), out=str(result_path))
    return 0 if pass_count == len(cases) else 1


def _excerpt(report: dict) -> dict:
    if not report:
        return {}
    return {
        "ticker": report.get("company_ticker"),
        "summary": (report.get("analysis_summary") or "")[:200],
        "key_findings": report.get("key_findings"),
        "degraded": report.get("degraded"),
        "triggers_fired": report.get("triggers_fired"),
        "tools_used": report.get("tools_used"),
    }


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
