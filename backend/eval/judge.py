"""LLM-as-judge scoring harness.

Given a candidate report and a rubric, asks an LLM to score 0–5 on each
dimension and returns the mean. CI passes if mean >= 4.0.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from app.llm.budget import JobBudget
from app.llm.client import LLMClient

RUBRIC = (Path(__file__).parent / "rubric.md").read_text()


_JUDGE_SYSTEM = """You are a strict evaluator scoring an autonomous market
research agent's output. Use ONLY the rubric provided. Output ONLY JSON:
{
  "factuality": int 0-5,
  "schema_compliance": int 0-5,
  "citation_presence": int 0-5,
  "findings_actionability": int 0-5,
  "sentiment_plausibility": int 0-5,
  "rationale": "one short paragraph"
}"""


async def score(report: dict) -> dict:
    budget = JobBudget.from_settings()
    llm = LLMClient(budget)
    resp = await llm.chat(
        messages=[
            {"role": "system", "content": _JUDGE_SYSTEM + "\n\nRUBRIC:\n" + RUBRIC},
            {"role": "user", "content": json.dumps(report, default=str)[:8000]},
        ],
        response_format={"type": "json_object"},
        temperature=0.0,
    )
    raw = resp.choices[0].message.content or "{}"
    return json.loads(raw)


async def mean_score(report: dict) -> float:
    s = await score(report)
    keys = [
        "factuality",
        "schema_compliance",
        "citation_presence",
        "findings_actionability",
        "sentiment_plausibility",
    ]
    nums = [float(s.get(k, 0)) for k in keys]
    return sum(nums) / len(nums)


if __name__ == "__main__":
    import sys

    path = Path(sys.argv[1])
    rpt = json.loads(path.read_text())
    print(json.dumps(asyncio.run(score(rpt)), indent=2))
