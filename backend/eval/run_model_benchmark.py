"""Lean model bake-off: GPT-5.4 vs Grok 4.3 vs DeepSeek V4 Pro.

Hits each OpenRouter model directly with three representative agent-style
prompts (planner tool-call, news sentiment classification, final JSON
synthesis) and measures latency + tokens + cost. No DB, no Redis, no graph
state. Purely model-quality + economics.

Usage:
    python -m eval.run_model_benchmark

Reads OPENROUTER_API_KEY from env or ../.env.
"""

from __future__ import annotations

import asyncio
import json
import os
import statistics
import time
from datetime import UTC, datetime
from pathlib import Path

from openai import AsyncOpenAI

ROOT = Path(__file__).resolve().parents[2]
REPORT = ROOT / "docs" / "model_benchmark.md"
RESULTS_DIR = Path(__file__).parent / "results"

# Load .env minimally so we don't need pydantic-settings.
for p in (ROOT / ".env", ROOT / "backend" / ".env"):
    if p.exists():
        for line in p.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
if not API_KEY:
    raise SystemExit("OPENROUTER_API_KEY not set (env or .env)")

# Per-million-token pricing, USD. Verified against OpenRouter /models on 2026-05-16.
MODELS = [
    {"id": "openai/gpt-5.4",          "display": "GPT-5.4",         "in": 2.50,  "out": 15.00},
    {"id": "x-ai/grok-4.3",           "display": "Grok 4.3",        "in": 1.25,  "out": 2.50},
    {"id": "deepseek/deepseek-v4-pro","display": "DeepSeek V4 Pro", "in": 0.435, "out": 0.87},
]

# Tool schema mirrors what the real M.I.R.A. planner exposes.
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_market_data",
            "description": "Fetch price/volume/market-cap/P-E/52w/last-two-quarterly-revenues for a ticker.",
            "parameters": {
                "type": "object",
                "properties": {"ticker": {"type": "string"}},
                "required": ["ticker"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_news_sentiment",
            "description": "Fetch the 5 most recent news articles for a ticker and tag sentiment.",
            "parameters": {
                "type": "object",
                "properties": {"ticker": {"type": "string"}},
                "required": ["ticker"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_correlation",
            "description": "Compute Pearson correlation of the ticker vs SP500, sector ETF, and peers.",
            "parameters": {
                "type": "object",
                "properties": {
                    "ticker": {"type": "string"},
                    "peers": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["ticker"],
            },
        },
    },
]

# Three representative tasks the M.I.R.A. agent actually performs.
TASKS = [
    {
        "name": "planner_tool_call",
        "description": "Decide which tools to call for a fresh ticker query.",
        "kind": "tools",
        "messages": [
            {"role": "system", "content": (
                "You are M.I.R.A., a market-research agent. Given a user query, decide "
                "which tools to invoke first. Respond ONLY by calling tools — no prose. "
                "You should call all three of get_market_data, get_news_sentiment, and "
                "get_correlation in parallel on the target ticker."
            )},
            {"role": "user", "content": "Analyze the near-term prospects of Tesla (TSLA)."},
        ],
    },
    {
        "name": "news_sentiment",
        "description": "Classify five news headlines as positive/negative/neutral.",
        "kind": "chat",
        "messages": [
            {"role": "system", "content": (
                "You are a financial-news sentiment classifier. For each headline, "
                "return a JSON array of objects {headline, sentiment, score} where "
                "sentiment ∈ {positive,negative,neutral} and score ∈ [-1,1]. "
                "Return ONLY the JSON, no prose."
            )},
            {"role": "user", "content": json.dumps([
                "Apple beats Q1 earnings, raises full-year guidance",
                "Apple faces EU antitrust probe over App Store fees",
                "Apple unveils new M5 chip with 30% performance gain",
                "Analyst downgrades Apple citing China iPhone weakness",
                "Apple announces $90B share buyback program",
            ])},
        ],
    },
    {
        "name": "synthesis_json",
        "description": "Produce the final structured AnalysisReport from tool results.",
        "kind": "chat",
        "messages": [
            {"role": "system", "content": (
                "You are M.I.R.A.'s synthesizer. Output ONLY a JSON object matching "
                "this schema: {company_ticker, company_name, analysis_summary, "
                "sentiment_score (float -1..1), key_findings (exactly 3 strings), "
                "tools_used (array of strings), generated_at (ISO 8601 string)}."
            )},
            {"role": "user", "content": (
                "Tool results:\n"
                "market_data: {ticker:'MSFT', price:412.50, change_pct:0.8, market_cap:3.06e12, pe:35.2}\n"
                "news_sentiment: {distribution:{positive:3,negative:1,neutral:1}, score:0.32}\n"
                "correlation: {vs_sp500:0.81, vs_sector_etf_XLK:0.92, vs_peers:{GOOGL:0.71}}\n"
                "Synthesize the report."
            )},
        ],
    },
]


def cost(model: dict, prompt_tokens: int, completion_tokens: int) -> float:
    return (prompt_tokens * model["in"] + completion_tokens * model["out"]) / 1_000_000


async def run_task(client: AsyncOpenAI, model: dict, task: dict) -> dict:
    t0 = time.monotonic()
    try:
        kwargs = {
            "model": model["id"],
            "messages": task["messages"],
            "temperature": 0.2,
            "max_tokens": 1024,
        }
        if task["kind"] == "tools":
            kwargs["tools"] = TOOLS
            kwargs["tool_choice"] = "auto"
        resp = await client.chat.completions.create(**kwargs)
        latency = time.monotonic() - t0
        u = resp.usage
        pt, ct = (u.prompt_tokens or 0, u.completion_tokens or 0) if u else (0, 0)
        msg = resp.choices[0].message
        # Validate output shape per task kind.
        ok, note = True, ""
        if task["kind"] == "tools":
            tc = getattr(msg, "tool_calls", None) or []
            names = [t.function.name for t in tc]
            ok = bool(tc) and "get_market_data" in names
            note = f"tools_called={len(tc)}: {','.join(names) or '—'}"
        else:
            content = (msg.content or "").strip().lstrip("```json").lstrip("```").rstrip("```").strip()
            try:
                parsed = json.loads(content)
                if task["name"] == "synthesis_json":
                    ok = (
                        isinstance(parsed, dict)
                        and parsed.get("company_ticker") == "MSFT"
                        and len(parsed.get("key_findings") or []) == 3
                        and -1 <= float(parsed.get("sentiment_score", -99)) <= 1
                    )
                    note = "schema valid" if ok else f"schema fail: {list(parsed)[:5]}"
                else:
                    ok = isinstance(parsed, list) and len(parsed) == 5 and all(
                        "sentiment" in i for i in parsed
                    )
                    note = f"classified {len(parsed) if isinstance(parsed, list) else 0}/5"
            except Exception as e:  # noqa: BLE001
                ok, note = False, f"non-JSON: {str(e)[:50]}"
        return {
            "task": task["name"], "ok": ok, "note": note,
            "latency_s": round(latency, 2),
            "prompt_tokens": pt, "completion_tokens": ct,
            "cost_usd": round(cost(model, pt, ct), 6),
        }
    except Exception as e:  # noqa: BLE001
        return {
            "task": task["name"], "ok": False,
            "note": f"ERROR: {type(e).__name__}: {str(e)[:80]}",
            "latency_s": round(time.monotonic() - t0, 2),
            "prompt_tokens": 0, "completion_tokens": 0, "cost_usd": 0.0,
        }


async def main() -> int:
    client = AsyncOpenAI(
        api_key=API_KEY,
        base_url="https://openrouter.ai/api/v1",
        timeout=120,
        default_headers={"HTTP-Referer": "https://github.com/shady-abdelaziz/market-intelligence-research-agent", "X-Title": "M.I.R.A. bench"},
    )

    results: dict[str, dict] = {}
    for m in MODELS:
        print(f"\n=== {m['display']} ({m['id']}) ===", flush=True)
        runs = []
        for task in TASKS:
            r = await run_task(client, m, task)
            mark = "✅" if r["ok"] else "❌"
            print(f"  {mark} {r['task']:<20} {r['latency_s']:>5}s  p={r['prompt_tokens']:>4} c={r['completion_tokens']:>4}  ${r['cost_usd']:.5f}  {r['note']}", flush=True)
            runs.append(r)
        lat = [r["latency_s"] for r in runs]
        results[m["id"]] = {
            "display": m["display"],
            "runs": runs,
            "passed": sum(1 for r in runs if r["ok"]),
            "total": len(runs),
            "p50_latency_s": round(statistics.median(lat), 2),
            "avg_latency_s": round(statistics.mean(lat), 2),
            "total_prompt": sum(r["prompt_tokens"] for r in runs),
            "total_completion": sum(r["completion_tokens"] for r in runs),
            "total_cost_usd": round(sum(r["cost_usd"] for r in runs), 5),
        }

    RESULTS_DIR.mkdir(exist_ok=True)
    ts = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    out_json = RESULTS_DIR / f"benchmark-{ts}.json"
    out_json.write_text(json.dumps(results, indent=2))
    REPORT.parent.mkdir(exist_ok=True)
    REPORT.write_text(render_md(results))
    print(f"\nWrote {out_json}")
    print(f"Wrote {REPORT}")
    pdf_path = _try_render_pdf(REPORT)
    if pdf_path:
        print(f"Wrote {pdf_path}")
    return 0


def _try_render_pdf(md_path: Path) -> Path | None:
    """Best-effort: render the Markdown report to PDF if weasyprint+markdown are installed."""
    try:
        import markdown as _md
        from weasyprint import HTML
    except ImportError:
        print("(skipped PDF: pip install weasyprint markdown to enable)")
        return None
    html = _md.markdown(md_path.read_text(), extensions=["tables", "fenced_code"])
    css = (
        "@page { size: A4; margin: 1.5cm; }"
        "body { font-family: -apple-system, BlinkMacSystemFont, Arial, sans-serif; "
        "font-size: 10pt; color: #1a1a1a; line-height: 1.5; }"
        "h1 { font-size: 22pt; border-bottom: 2px solid #333; padding-bottom: 6px; }"
        "h2 { font-size: 14pt; margin-top: 20px; color: #222; }"
        "h3 { font-size: 11pt; color: #444; margin-top: 14px; }"
        "table { border-collapse: collapse; width: 100%; margin: 8px 0; font-size: 9pt; }"
        "th, td { border: 1px solid #ccc; padding: 4px 8px; text-align: left; }"
        "th { background: #f0f0f0; font-weight: 600; }"
        "code { font-family: ui-monospace, Menlo, Consolas, monospace; font-size: 9pt; "
        "background: #f4f4f4; padding: 1px 4px; border-radius: 3px; }"
        "pre { background: #f4f4f4; padding: 8px; border-radius: 4px; font-size: 9pt; }"
        "em { color: #666; }"
    )
    pdf_path = md_path.with_suffix(".pdf")
    HTML(string=f"<style>{css}</style>{html}").write_pdf(str(pdf_path))
    return pdf_path


def render_md(results: dict) -> str:
    ts = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        "# Model bake-off — M.I.R.A. agent tasks",
        "",
        f"_Generated: {ts} via `python -m eval.run_model_benchmark`_",
        "",
        "Three representative tasks from the M.I.R.A. agent (planner tool-calling, "
        "news-sentiment classification, structured-JSON synthesis) executed against "
        "each model through OpenRouter. Measures correctness, latency, tokens, cost.",
        "",
        "## Summary",
        "",
        "| Model | Pass | p50 latency | Avg latency | Total tokens | Total cost |",
        "|---|---|---|---|---|---|",
    ]
    for mid, r in results.items():
        lines.append(
            f"| **{r['display']}** (`{mid}`) | {r['passed']}/{r['total']} "
            f"| {r['p50_latency_s']}s | {r['avg_latency_s']}s "
            f"| {r['total_prompt']+r['total_completion']:,} "
            f"| ${r['total_cost_usd']:.5f} |"
        )
    lines += ["", "## Per-task detail", ""]
    task_names = [t["name"] for t in TASKS]
    for tn in task_names:
        lines += [
            f"### `{tn}`",
            "",
            "| Model | Pass | Latency | Prompt tok | Completion tok | Cost | Note |",
            "|---|---|---|---|---|---|---|",
        ]
        for mid, r in results.items():
            run = next(x for x in r["runs"] if x["task"] == tn)
            lines.append(
                f"| {r['display']} | {'✅' if run['ok'] else '❌'} "
                f"| {run['latency_s']}s | {run['prompt_tokens']} | {run['completion_tokens']} "
                f"| ${run['cost_usd']:.5f} | {run['note']} |"
            )
        lines.append("")

    # Verdict
    by_cost = sorted(results.values(), key=lambda r: r["total_cost_usd"])
    by_lat = sorted(results.values(), key=lambda r: r["p50_latency_s"])
    by_pass = sorted(results.values(), key=lambda r: -r["passed"])
    lines += [
        "## Verdict",
        "",
        f"- **Highest pass rate**: {by_pass[0]['display']} ({by_pass[0]['passed']}/{by_pass[0]['total']})",
        f"- **Fastest (p50)**: {by_lat[0]['display']} ({by_lat[0]['p50_latency_s']}s)",
        f"- **Cheapest**: {by_cost[0]['display']} (${by_cost[0]['total_cost_usd']:.5f})",
        "",
        "## Methodology",
        "",
        "- Driver: `backend/eval/run_model_benchmark.py`.",
        "- Tasks mirror the real M.I.R.A. agent: (1) planner emits tool calls, "
        "(2) news-sentiment classifier returns JSON array, (3) synthesizer emits "
        "the final `AnalysisReport`-shaped JSON.",
        "- Pass = task-specific structural check (correct tool names called; "
        "valid JSON of the right shape; sentiment in [-1,1]; exactly 3 key_findings).",
        "- Cost = `(prompt × in_rate + completion × out_rate) / 1e6`, "
        "rates verified against OpenRouter `/models` on 2026-05-16.",
        "",
        "## Re-run",
        "",
        "```bash",
        "cd backend && python -m eval.run_model_benchmark",
        "```",
        "",
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
