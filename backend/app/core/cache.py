"""
Redis is used for exactly one thing in this project: caching the computed
group balance summary (net balances + simplified settlements), which is the
single most expensive read in the app — it requires pulling every expense
and every expense_split row for a group and running the settlement
algorithm over them. Everything else (auth, expenses, payments) reads
straight from Postgres because there's no repeated-computation cost to
amortize.

Cache invalidation strategy: rather than trying to surgically invalidate on
every possible write, we simply delete the group's cache key whenever an
expense is added/deleted or a settlement's status changes. Combined with a
short TTL as a backstop, this keeps the cache trivially correct at the cost
of occasionally recomputing more than strictly necessary — the right
trade-off for a group of a few people's worth of expenses.
"""

import json
from typing import Any, Optional

import redis

from app.core.config import settings

_redis_client: Optional[redis.Redis] = None


def get_redis() -> Optional[redis.Redis]:
    """
    Returns a Redis client, or None if Redis is unreachable. Caching is a
    performance optimization, never a correctness requirement — if Redis is
    down, callers must fall back to computing straight from Postgres rather
    than failing the request.
    """
    global _redis_client
    if _redis_client is None:
        try:
            _redis_client = redis.from_url(settings.REDIS_URL, socket_connect_timeout=1)
            _redis_client.ping()
        except Exception:
            return None
    return _redis_client


def cache_get_json(key: str) -> Optional[Any]:
    client = get_redis()
    if client is None:
        return None
    try:
        raw = client.get(key)
        return json.loads(raw) if raw else None
    except Exception:
        return None


def cache_set_json(key: str, value: Any, ttl_seconds: Optional[int] = None) -> None:
    client = get_redis()
    if client is None:
        return
    try:
        client.set(key, json.dumps(value), ex=ttl_seconds or settings.CACHE_TTL_SECONDS)
    except Exception:
        pass


def cache_delete(key: str) -> None:
    client = get_redis()
    if client is None:
        return
    try:
        client.delete(key)
    except Exception:
        pass


def group_summary_cache_key(group_id: str) -> str:
    return f"group_summary:{group_id}"
