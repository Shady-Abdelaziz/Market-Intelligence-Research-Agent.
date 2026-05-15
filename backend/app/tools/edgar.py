"""SEC EDGAR tool — fetches recent 10-K/10-Q/8-K filings for the ticker.

Used as the reflection fallback when news is stale. SEC requires a
User-Agent identifying the caller and respects a 10 req/sec rate limit.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from app.cache.redis_cache import get as cache_get
from app.cache.redis_cache import set as cache_set
from app.config import get_settings
from app.resilience.http_client import get_client
from app.tools.base import Tool

_settings = get_settings()


async def _resolve_cik(ticker: str) -> str | None:
    cached = await cache_get("edgar", f"cik:{ticker}")
    if cached:
        return cached
    client = get_client()
    r = await client.get(
        "https://www.sec.gov/cgi-bin/browse-edgar",
        params={"action": "getcompany", "CIK": ticker, "type": "10-K", "output": "atom"},
        headers={"User-Agent": _settings.edgar_user_agent},
    )
    if r.status_code != 200:
        # Fallback: company tickers JSON
        r2 = await client.get(
            "https://www.sec.gov/files/company_tickers.json",
            headers={"User-Agent": _settings.edgar_user_agent},
        )
        if r2.status_code != 200:
            return None
        for _, entry in r2.json().items():
            if entry.get("ticker", "").upper() == ticker.upper():
                cik = str(entry["cik_str"]).zfill(10)
                await cache_set("edgar", f"cik:{ticker}", cik, _settings.cache_ttl_edgar)
                return cik
        return None
    # Parse CIK out of the atom feed (cheap heuristic)
    import re

    m = re.search(r"CIK=(\d+)", r.text)
    if m:
        cik = m.group(1).zfill(10)
        await cache_set("edgar", f"cik:{ticker}", cik, _settings.cache_ttl_edgar)
        return cik
    return None


class EdgarTool(Tool):
    name = "edgar_filings"
    upstream = "edgar"

    def schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": (
                    "Fetch recent SEC EDGAR filings (10-K, 10-Q, 8-K) for a "
                    "ticker. Useful as a fallback when news is stale or "
                    "official corporate disclosures are needed."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "ticker": {"type": "string"},
                        "days": {"type": "integer", "default": 30},
                    },
                    "required": ["ticker"],
                },
            },
        }

    async def _run(self, ticker: str, days: int = 30) -> dict[str, Any]:
        ticker = ticker.upper().strip()
        cache_key = f"filings:{ticker}:{days}"
        cached = await cache_get("edgar", cache_key)
        if cached:
            return cached

        cik = await _resolve_cik(ticker)
        if not cik:
            return {"ticker": ticker, "filings": [], "error": "CIK_NOT_FOUND"}

        client = get_client()
        r = await client.get(
            f"https://data.sec.gov/submissions/CIK{cik}.json",
            headers={"User-Agent": _settings.edgar_user_agent},
        )
        if r.status_code != 200:
            return {"ticker": ticker, "filings": [], "error": f"HTTP_{r.status_code}"}

        data = r.json()
        recent = data.get("filings", {}).get("recent", {}) or {}
        forms = recent.get("form", []) or []
        dates = recent.get("filingDate", []) or []
        accessions = recent.get("accessionNumber", []) or []
        primary_docs = recent.get("primaryDocument", []) or []

        cutoff = datetime.now(UTC).date() - timedelta(days=days)
        wanted = {"10-K", "10-Q", "8-K"}
        filings = []
        for form, date_str, acc, doc in zip(forms, dates, accessions, primary_docs, strict=False):
            if form not in wanted:
                continue
            try:
                date_d = datetime.fromisoformat(date_str).date()
            except Exception:
                continue
            if date_d < cutoff:
                continue
            acc_clean = acc.replace("-", "")
            filings.append(
                {
                    "form": form,
                    "filed_on": date_str,
                    "accession": acc,
                    "url": f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc_clean}/{doc}",
                }
            )
            if len(filings) >= 10:
                break

        result = {"ticker": ticker, "cik": cik, "filings": filings}
        await cache_set("edgar", cache_key, result, _settings.cache_ttl_edgar)
        return result

    def summarize(self, output: dict[str, Any]) -> str:
        return f"{len(output.get('filings', []))} recent SEC filings for {output.get('ticker')}"
