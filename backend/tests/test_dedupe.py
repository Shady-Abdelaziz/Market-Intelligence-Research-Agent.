from __future__ import annotations

from app.cache.dedupe import dedup_keep_last_n, normalize_url, title_fingerprint, url_hash


def test_normalize_strips_utm():
    a = "https://Example.COM/news/?utm_source=twitter&id=42"
    b = "https://example.com/news?id=42"
    assert normalize_url(a) == normalize_url(b)


def test_url_hash_stable():
    h1 = url_hash("https://example.com/x?utm_source=a")
    h2 = url_hash("https://example.com/x")
    assert h1 == h2


def test_title_fingerprint_catches_minor_variations():
    a = title_fingerprint("Apple posts record earnings in Q1!")
    b = title_fingerprint("apple   posts record earnings in q1")
    assert a == b


def test_dedup_keep_last_n_preserves_order():
    # Contract: dedup by first occurrence, then keep the last N from the
    # deduped list. So ["a","b","a","c","b","d"] -> ["a","b","c","d"] -> last 3.
    out = dedup_keep_last_n(["a", "b", "a", "c", "b", "d"], n=3)
    assert out == ["b", "c", "d"]
    assert len(set(out)) == len(out)
