"""Date parsing helpers shared across agent nodes."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any


def parse_published_at(value: Any) -> datetime | None:
    """Best-effort parse of a published_at value.

    Accepts:
      - datetime: returned as-is (naïve assumed UTC).
      - str: ISO 8601 with trailing Z, explicit ±HH:MM offset, or naïve (assume UTC).
      - int/float: epoch seconds.
    Returns None on unparseable input.
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if isinstance(value, bool):
        # bool is a subclass of int — reject explicitly so True/False don't become epoch 1/0
        return None
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(float(value), tz=UTC)
        except (OverflowError, OSError, ValueError):
            return None
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return None
        try:
            dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        except ValueError:
            return None
        return dt if dt.tzinfo else dt.replace(tzinfo=UTC)
    return None
