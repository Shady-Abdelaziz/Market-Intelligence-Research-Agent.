"""Shared slowapi Limiter — single source of truth so the middleware in
main.py and the route decorators in api/*.py track the same counters."""

from __future__ import annotations

from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
