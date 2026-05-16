# Model bake-off — M.I.R.A. agent tasks

_Generated: 2026-05-16 17:05 UTC via `python -m eval.run_model_benchmark`_

Three representative tasks from the M.I.R.A. agent (planner tool-calling, news-sentiment classification, structured-JSON synthesis) executed against each model through OpenRouter. Measures correctness, latency, tokens, cost.

## Summary

| Model | Pass | p50 latency | Avg latency | Total tokens | Total cost |
|---|---|---|---|---|---|
| **GPT-5.4** (`openai/gpt-5.4`) | 3/3 | 2.8s | 3.02s | 1,071 | $0.00969 |
| **Grok 4.3** (`x-ai/grok-4.3`) | 3/3 | 6.21s | 5.66s | 2,914 | $0.00605 |
| **DeepSeek V4 Pro** (`deepseek/deepseek-v4-pro`) | 3/3 | 16.42s | 17.41s | 1,827 | $0.00123 |

## Per-task detail

### `planner_tool_call`

| Model | Pass | Latency | Prompt tok | Completion tok | Cost | Note |
|---|---|---|---|---|---|---|
| GPT-5.4 | ✅ | 1.77s | 202 | 84 | $0.00177 | tools_called=3: get_market_data,get_news_sentiment,get_correlation |
| Grok 4.3 | ✅ | 3.48s | 443 | 399 | $0.00155 | tools_called=3: get_market_data,get_news_sentiment,get_correlation |
| DeepSeek V4 Pro | ✅ | 4.04s | 510 | 174 | $0.00037 | tools_called=3: get_market_data,get_news_sentiment,get_correlation |

### `news_sentiment`

| Model | Pass | Latency | Prompt tok | Completion tok | Cost | Note |
|---|---|---|---|---|---|---|
| GPT-5.4 | ✅ | 2.8s | 126 | 194 | $0.00323 | classified 5/5 |
| Grok 4.3 | ✅ | 6.21s | 244 | 541 | $0.00166 | classified 5/5 |
| DeepSeek V4 Pro | ✅ | 31.76s | 117 | 408 | $0.00041 | classified 5/5 |

### `synthesis_json`

| Model | Pass | Latency | Prompt tok | Completion tok | Cost | Note |
|---|---|---|---|---|---|---|
| GPT-5.4 | ✅ | 4.49s | 182 | 283 | $0.00470 | schema valid |
| Grok 4.3 | ✅ | 7.3s | 301 | 986 | $0.00284 | schema valid |
| DeepSeek V4 Pro | ✅ | 16.42s | 187 | 431 | $0.00046 | schema valid |

## Verdict

- **Highest pass rate**: GPT-5.4 (3/3)
- **Fastest (p50)**: GPT-5.4 (2.8s)
- **Cheapest**: DeepSeek V4 Pro ($0.00123)

## Methodology

- Driver: `backend/eval/run_model_benchmark.py`.
- Tasks mirror the real M.I.R.A. agent: (1) planner emits tool calls, (2) news-sentiment classifier returns JSON array, (3) synthesizer emits the final `AnalysisReport`-shaped JSON.
- Pass = task-specific structural check (correct tool names called; valid JSON of the right shape; sentiment in [-1,1]; exactly 3 key_findings).
- Cost = `(prompt × in_rate + completion × out_rate) / 1e6`, rates verified against OpenRouter `/models` on 2026-05-16.

## Re-run

```bash
cd backend && python -m eval.run_model_benchmark
```
