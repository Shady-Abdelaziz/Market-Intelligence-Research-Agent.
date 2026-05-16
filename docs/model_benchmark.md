# Model Bake-Off - M.I.R.A. Agent Tasks

Generated: 2026-05-16 17:05 UTC via `python -m eval.run_model_benchmark`.

Three representative M.I.R.A. agent tasks were executed through OpenRouter:

1. planner tool-call selection
2. news-sentiment classification
3. structured JSON synthesis

The benchmark measures pass/fail behavior, latency, token usage, and estimated cost.

## Summary

| Model | Pass | p50 latency | Avg latency | Total tokens | Total cost |
|---|---:|---:|---:|---:|---:|
| GPT-5.4 (`openai/gpt-5.4`) | 3/3 | 2.8s | 3.02s | 1,071 | $0.00969 |
| Grok 4.3 (`x-ai/grok-4.3`) | 3/3 | 6.21s | 5.66s | 2,914 | $0.00605 |
| DeepSeek V4 Pro (`deepseek/deepseek-v4-pro`) | 3/3 | 16.42s | 17.41s | 1,827 | $0.00123 |

## Per-Task Detail

### `planner_tool_call`

| Model | Pass | Latency | Prompt tok | Completion tok | Cost | Note |
|---|---:|---:|---:|---:|---:|---|
| GPT-5.4 | yes | 1.77s | 202 | 84 | $0.00177 | tools_called=3: get_market_data, get_news_sentiment, get_correlation |
| Grok 4.3 | yes | 3.48s | 443 | 399 | $0.00155 | tools_called=3: get_market_data, get_news_sentiment, get_correlation |
| DeepSeek V4 Pro | yes | 4.04s | 510 | 174 | $0.00037 | tools_called=3: get_market_data, get_news_sentiment, get_correlation |

### `news_sentiment`

| Model | Pass | Latency | Prompt tok | Completion tok | Cost | Note |
|---|---:|---:|---:|---:|---:|---|
| GPT-5.4 | yes | 2.8s | 126 | 194 | $0.00323 | classified 5/5 |
| Grok 4.3 | yes | 6.21s | 244 | 541 | $0.00166 | classified 5/5 |
| DeepSeek V4 Pro | yes | 31.76s | 117 | 408 | $0.00041 | classified 5/5 |

### `synthesis_json`

| Model | Pass | Latency | Prompt tok | Completion tok | Cost | Note |
|---|---:|---:|---:|---:|---:|---|
| GPT-5.4 | yes | 4.49s | 182 | 283 | $0.00470 | schema valid |
| Grok 4.3 | yes | 7.3s | 301 | 986 | $0.00284 | schema valid |
| DeepSeek V4 Pro | yes | 16.42s | 187 | 431 | $0.00046 | schema valid |

## Verdict

| Selection | Model | Why |
|---|---|---|
| Fastest | GPT-5.4 | lowest p50 latency at 2.8s |
| Cheapest | DeepSeek V4 Pro | lowest total benchmark cost at $0.00123 |
| Primary for this app | Grok 4.3 | passed all tasks while costing less than GPT-5.4 |
| Fallback for this app | DeepSeek V4 Pro | passed all tasks at the lowest cost, acceptable as a slower backup |

## Methodology

- Driver: `backend/eval/run_model_benchmark.py`.
- Tasks mirror the real M.I.R.A. agent: planner emits tool calls, news sentiment returns a JSON array, and synthesis returns `AnalysisReport`-shaped JSON.
- Pass criteria are structural: correct tool names, valid JSON, sentiment in `[-1, 1]`, and exactly three `key_findings`.
- Cost formula: `(prompt_tokens * input_rate + completion_tokens * output_rate) / 1e6`.
- Rates were verified against OpenRouter `/models` on 2026-05-16.

## Re-Run

```bash
cd backend
python -m eval.run_model_benchmark
```
