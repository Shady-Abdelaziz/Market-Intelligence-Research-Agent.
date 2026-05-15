# LLM-as-Judge Rubric

Each dimension scored 0–5 (5 = excellent, 0 = unusable).

1. **Factuality** — Do the figures in `market_snapshot` and `correlation_analysis` look plausible vs. the underlying tool outputs? Do citations correspond to real-looking news articles? Are quoted prices in a sane range for the ticker?

2. **Schema compliance** — Does the JSON parse and pass Pydantic validation? Exactly 3 `key_findings`? `sentiment_score` in [-1,1]? `tools_used` in chronological order?

3. **Citation presence** — Is `citation_sources` non-empty when `news_sentiment` was called? Are URLs not obviously hallucinated?

4. **Findings actionability** — Each of the 3 `key_findings` should describe a *concrete* takeaway (a metric, a comparison, a directional signal), not generic boilerplate ("the company has earnings").

5. **Sentiment plausibility** — Does `sentiment_score` reasonably match the dominant tone of the articles (look at `sentiment_distribution`)? Strong skew in one direction should not produce a near-zero overall.

Threshold: mean ≥ 4.0 across all golden cases.
