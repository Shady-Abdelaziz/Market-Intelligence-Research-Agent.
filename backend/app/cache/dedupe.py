"""URL normalization, hashing, and title fingerprinting for article dedup."""

from __future__ import annotations

import hashlib
import re
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

_TRACKING_PARAMS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "fbclid", "gclid", "mc_cid", "mc_eid", "ref",
}


def normalize_url(url: str) -> str:
    """Lowercase host, strip tracking params, remove trailing slash on path."""
    parsed = urlparse(url.strip())
    host = parsed.netloc.lower()
    path = parsed.path.rstrip("/") or "/"
    cleaned_query = [
        (k, v) for k, v in parse_qsl(parsed.query, keep_blank_values=True)
        if k.lower() not in _TRACKING_PARAMS
    ]
    return urlunparse(
        (parsed.scheme.lower(), host, path, "", urlencode(cleaned_query), "")
    )


def url_hash(url: str) -> str:
    return hashlib.sha256(normalize_url(url).encode("utf-8")).hexdigest()


def title_fingerprint(title: str | None) -> str | None:
    """Shingled fingerprint for near-duplicate titles (catches cross-posts)."""
    if not title:
        return None
    lowered = re.sub(r"\s+", " ", title.lower().strip())
    cleaned = re.sub(r"[^\w\s]", "", lowered)
    tokens = cleaned.split()
    if len(tokens) < 3:
        return hashlib.sha256(lowered.encode("utf-8")).hexdigest()
    shingles = sorted({" ".join(tokens[i:i + 3]) for i in range(len(tokens) - 2)})
    return hashlib.sha256(" ".join(shingles).encode("utf-8")).hexdigest()


def dedup_keep_last_n(urls: list[str], n: int = 50) -> list[str]:
    """Keep insertion-order uniqueness, return last n entries."""
    seen: set[str] = set()
    out: list[str] = []
    for u in urls:
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out[-n:]
