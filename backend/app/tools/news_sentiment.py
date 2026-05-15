"""Tool 2: News retrieval + sentiment.

Pipeline:
1. Fetch top-5 most-recent relevant articles from NewsAPI (filtered by
   title/description containing ticker or company name).
2. Cross-check with Marketaux for the same ticker (this also provides
   pre-computed sentiment tags as a second opinion).
3. Per-article sentiment via the LLM (Grok 4.3) — returns positive/neutral/
   negative + score in [-1,1] + rationale.
4. Aggregate into a distribution and a single overall score.

README documents the trade-off: LLM sentiment is flexible and explains its
reasoning, but is slower and noisier than a finance-tuned classifier like
FinBERT. We avoid local ML inference to keep image size and RAM small.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
from datetime import UTC, datetime
from typing import Any

from app.cache.dedupe import normalize_url, title_fingerprint, url_hash
from app.cache.redis_cache import get as cache_get
from app.cache.redis_cache import set as cache_set
from app.config import get_settings
from app.llm.budget import JobBudget
from app.llm.client import LLMClient
from app.resilience.http_client import get_client
from app.tools.base import Tool

_settings = get_settings()


async def _fetch_newsapi(ticker: str, company_name: str | None) -> list[dict[str, Any]]:
    if not _settings.newsapi_key:
        return []
    client = get_client()
    q_parts = [ticker]
    if company_name:
        q_parts.append(f'"{company_name}"')
    q = " OR ".join(q_parts)
    params = {
        "q": q,
        "language": "en",
        "sortBy": "publishedAt",
        "pageSize": 10,
        "apiKey": _settings.newsapi_key,
    }
    r = await client.get("https://newsapi.org/v2/everything", params=params)
    r.raise_for_status()
    data = r.json()
    out = []
    for art in data.get("articles", []):
        out.append(
            {
                "url": art.get("url"),
                "title": art.get("title"),
                "description": art.get("description"),
                "source": (art.get("source") or {}).get("name"),
                "published_at": art.get("publishedAt"),
                "provider": "newsapi",
            }
        )
    return out


async def _fetch_marketaux(ticker: str) -> list[dict[str, Any]]:
    if not _settings.marketaux_key:
        return []
    client = get_client()
    params = {
        "symbols": ticker,
        "language": "en",
        "filter_entities": "true",
        "limit": 10,
        "api_token": _settings.marketaux_key,
    }
    r = await client.get("https://api.marketaux.com/v1/news/all", params=params)
    if r.status_code >= 400:
        return []
    data = r.json()
    out = []
    for art in data.get("data", []):
        entities = art.get("entities") or []
        ext_sent = None
        for e in entities:
            if (e.get("symbol") or "").upper() == ticker.upper():
                ext_sent = e.get("sentiment_score")
                break
        out.append(
            {
                "url": art.get("url"),
                "title": art.get("title"),
                "description": art.get("description") or art.get("snippet"),
                "source": art.get("source"),
                "published_at": art.get("published_at"),
                "provider": "marketaux",
                "marketaux_sentiment_score": ext_sent,
            }
        )
    return out


def _relevant(article: dict[str, Any], ticker: str, company_name: str | None) -> bool:
    text = " ".join(filter(None, [article.get("title"), article.get("description")])).lower()
    if not text:
        return False
    if ticker.lower() in text:
        return True
    return bool(company_name and company_name.lower().split()[0] in text)


def _parse_published(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        return None


def _merge_and_dedupe(*sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_hash: dict[str, dict[str, Any]] = {}
    by_fp: dict[str, dict[str, Any]] = {}
    for source in sources:
        for art in source:
            url = art.get("url")
            if not url:
                continue
            h = url_hash(url)
            fp = title_fingerprint(art.get("title"))
            existing = by_hash.get(h) or (by_fp.get(fp) if fp else None)
            if existing:
                # Merge marketaux sentiment if present
                if art.get("marketaux_sentiment_score") is not None:
                    existing.setdefault(
                        "marketaux_sentiment_score", art["marketaux_sentiment_score"]
                    )
                continue
            art["url_hash"] = h
            art["title_fingerprint"] = fp
            art["normalized_url"] = normalize_url(url)
            art["published_dt"] = _parse_published(art.get("published_at"))
            by_hash[h] = art
            if fp:
                by_fp[fp] = art
    merged = list(by_hash.values())
    merged.sort(
        key=lambda a: a.get("published_dt") or datetime.min.replace(tzinfo=UTC), reverse=True
    )
    return merged


_SENTIMENT_SYSTEM = """You are a financial news sentiment classifier.
For each article, output ONLY JSON with: {"label": "positive"|"negative"|"neutral", "score": float in [-1.0, 1.0], "rationale": "short reason"}.
Use the article's likely effect on the company's stock price as the signal."""


async def _classify_one(llm: LLMClient, article: dict[str, Any]) -> dict[str, Any]:
    text = f"Title: {article.get('title') or ''}\nDescription: {article.get('description') or ''}"
    messages = [
        {"role": "system", "content": _SENTIMENT_SYSTEM},
        {"role": "user", "content": text},
    ]
    try:
        resp = await llm.chat(
            messages=messages,
            response_format={"type": "json_object"},
            temperature=0.0,
        )
        content = resp.choices[0].message.content or "{}"
        parsed = json.loads(content)
        label = parsed.get("label", "neutral").lower()
        if label not in {"positive", "negative", "neutral"}:
            label = "neutral"
        score = float(parsed.get("score", 0.0))
        score = max(-1.0, min(1.0, score))
        return {"label": label, "score": score, "rationale": parsed.get("rationale", "")}
    except Exception as e:
        return {"label": "neutral", "score": 0.0, "rationale": f"classification_failed: {e}"}


class NewsSentimentTool(Tool):
    name = "news_sentiment"
    upstream = "newsapi"

    def __init__(self, llm_factory):
        self._llm_factory = llm_factory

    def schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": (
                    "Fetch the 5 most recent relevant news articles about a "
                    "company and classify each one's sentiment "
                    "(positive/negative/neutral) plus aggregate the distribution."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "ticker": {"type": "string"},
                        "company_name": {"type": "string"},
                    },
                    "required": ["ticker"],
                },
            },
        }

    async def _run(
        self,
        ticker: str,
        company_name: str | None = None,
        parent_budget: JobBudget | None = None,
    ) -> dict[str, Any]:
        budget = parent_budget
        ticker = ticker.upper().strip()
        cache_key = f"{ticker}:{(company_name or '').lower()}"
        cached = await cache_get("news", cache_key)
        if cached:
            return cached

        # 1) Fetch
        newsapi_arts, marketaux_arts = await asyncio.gather(
            _fetch_newsapi(ticker, company_name),
            _fetch_marketaux(ticker),
            return_exceptions=False,
        )
        merged = _merge_and_dedupe(newsapi_arts, marketaux_arts)
        relevant = [a for a in merged if _relevant(a, ticker, company_name)]
        if not relevant:
            relevant = merged  # fall back to anything
        top5 = relevant[:5]

        # 2) Classify
        if budget is None:
            budget = JobBudget.from_settings()
        llm = self._llm_factory(budget)
        sentiments = await asyncio.gather(*(_classify_one(llm, a) for a in top5))

        # 3) Aggregate
        articles_out = []
        pos = neg = neu = 0
        scores: list[float] = []
        cross_check_diffs: list[float] = []
        for art, s in zip(top5, sentiments, strict=True):
            articles_out.append(
                {
                    "url": art.get("url"),
                    "title": art.get("title"),
                    "source": art.get("source"),
                    "published_at": (art.get("published_at") if art.get("published_at") else None),
                    "sentiment": s["label"],
                    "sentiment_score": s["score"],
                    "rationale": s["rationale"],
                }
            )
            scores.append(s["score"])
            if s["label"] == "positive":
                pos += 1
            elif s["label"] == "negative":
                neg += 1
            else:
                neu += 1
            mx = art.get("marketaux_sentiment_score")
            if mx is not None:
                with contextlib.suppress(Exception):
                    cross_check_diffs.append(abs(float(mx) - s["score"]))

        overall = sum(scores) / len(scores) if scores else 0.0
        confidence = 1.0
        if cross_check_diffs:
            avg_diff = sum(cross_check_diffs) / len(cross_check_diffs)
            confidence = max(0.0, 1.0 - avg_diff)

        result = {
            "ticker": ticker,
            "articles": articles_out,
            "distribution": {
                "positive": pos,
                "negative": neg,
                "neutral": neu,
                "total": pos + neg + neu,
            },
            "overall_score": overall,
            "confidence": confidence,
            "fetched_at": datetime.now(UTC).isoformat(),
        }
        await cache_set("news", cache_key, result, _settings.cache_ttl_news)
        return result

    def summarize(self, output: dict[str, Any]) -> str:
        d = output.get("distribution", {})
        return (
            f"{output.get('ticker')}: {d.get('positive', 0)}+ "
            f"{d.get('neutral', 0)}~ {d.get('negative', 0)}- "
            f"(overall {output.get('overall_score', 0):.2f})"
        )
