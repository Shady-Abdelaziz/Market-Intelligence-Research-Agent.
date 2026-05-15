"""Tool 3 (mock half): simulates fetching peer fundamentals.

The brief explicitly says Tool 3 "simulates a mock API call returning a
company's last two quarterly revenue reports or recent stock price". We
provide this mock alongside the real correlation tool — the mock honours
the brief wording verbatim; correlation.py does the real work.

Returns canned-but-plausible numbers seeded by ticker so calls are stable
across runs.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone
from typing import Any

from app.tools.base import Tool


def _seeded_float(ticker: str, salt: str, lo: float, hi: float) -> float:
    h = hashlib.sha256(f"{ticker}:{salt}".encode()).digest()
    n = int.from_bytes(h[:8], "big") / 2**64
    return lo + n * (hi - lo)


class PeerFundamentalsTool(Tool):
    name = "peer_fundamentals"
    upstream = None  # mock, no external call

    def schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": (
                    "Simulated peer fundamentals API. Returns the last two "
                    "quarterly revenues and a recent stock price for each peer "
                    "ticker. Use this when you need quick peer-comparison data "
                    "without hitting a real financial data API."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "peers": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["peers"],
                },
            },
        }

    async def _run(self, peers: list[str]) -> dict[str, Any]:
        peers = [p.upper().strip() for p in peers]
        now = datetime.now(timezone.utc)
        out: dict[str, Any] = {"peers": {}}
        for p in peers:
            q1 = _seeded_float(p, "q1", 5e9, 80e9)
            q2 = q1 * _seeded_float(p, "q2g", 0.95, 1.10)
            recent_price = _seeded_float(p, "px", 30.0, 400.0)
            out["peers"][p] = {
                "ticker": p,
                "recent_price_usd": round(recent_price, 2),
                "last_two_quarterly_revenues": [
                    {
                        "quarter": f"{now.year} Q{((now.month - 1) // 3)}",
                        "revenue_usd": round(q2, 2),
                        "reported_at": (now - timedelta(days=45)).isoformat(),
                    },
                    {
                        "quarter": f"{now.year} Q{max(((now.month - 1) // 3) - 1, 1)}",
                        "revenue_usd": round(q1, 2),
                        "reported_at": (now - timedelta(days=135)).isoformat(),
                    },
                ],
            }
        return out

    def summarize(self, output: dict[str, Any]) -> str:
        peers = list(output.get("peers", {}).keys())
        return f"mock fundamentals for {peers}"
