"""
Redis is used for exactly one thing in this project: caching the computed
group balance snapshot, the single most expensive read in the app.

Correctness rules (these are what keep a cache from ever misleading a user
or the AI about money):

1. PostgreSQL is the source of truth. Anything that DECIDES something —
   validating a settlement, preparing/confirming an AI draft, answering an AI
   question — reads PostgreSQL directly and bypasses this cache
   (see balance_service.get_group_balances(use_cache=False)).
   The cache only accelerates display reads such as the group page.
2. Invalidation is tied to successful commits. Services call
   `invalidate_group_after_commit(db, group_id)`; the key is deleted only when
   the surrounding transaction actually commits, and the request is dropped if
   it rolls back. There is no window where the cache is cleared before the
   data changed, and no mutation path that can forget to clear it as long as
   it registers the group.
3. A short TTL is a backstop for the one race no invalidation scheme can
   remove (a reader that computed from old data and writes it after the
   writer's invalidation).
4. Redis being down must never fail a request. After a failure the client
   backs off for a few seconds instead of paying a connect timeout on every
   call, and every operation degrades to "cache miss".
"""
from __future__ import annotations

import json
import time
from typing import Any, Iterable, Optional

import redis
from sqlalchemy import event
from sqlalchemy.orm import Session

from app.core.config import settings

_redis_client: Optional[redis.Redis] = None
_retry_after: float = 0.0
_BACKOFF_SECONDS = 5.0
_INVALIDATION_KEY = "_group_cache_invalidations"


def get_redis() -> Optional[redis.Redis]:
    """Returns a Redis client, or None while Redis is unreachable."""
    global _redis_client, _retry_after
    if _redis_client is not None:
        return _redis_client
    if time.monotonic() < _retry_after:
        return None
    try:
        client = redis.from_url(
            settings.REDIS_URL, socket_connect_timeout=1, socket_timeout=1, decode_responses=False
        )
        client.ping()
        _redis_client = client
        return _redis_client
    except Exception:
        _retry_after = time.monotonic() + _BACKOFF_SECONDS
        return None


def _mark_unhealthy() -> None:
    """Drop the client after a runtime failure so the next call re-checks with back-off."""
    global _redis_client, _retry_after
    _redis_client = None
    _retry_after = time.monotonic() + _BACKOFF_SECONDS


def reset_cache_client() -> None:
    """Test helper: forget the client and any back-off state."""
    global _redis_client, _retry_after
    _redis_client = None
    _retry_after = 0.0


def cache_get_json(key: str) -> Optional[Any]:
    client = get_redis()
    if client is None:
        return None
    try:
        raw = client.get(key)
        return json.loads(raw) if raw else None
    except Exception:
        _mark_unhealthy()
        return None


def cache_set_json(key: str, value: Any, ttl_seconds: Optional[int] = None) -> None:
    client = get_redis()
    if client is None:
        return
    try:
        client.set(key, json.dumps(value), ex=ttl_seconds or settings.CACHE_TTL_SECONDS)
    except Exception:
        _mark_unhealthy()


def cache_delete(key: str) -> None:
    client = get_redis()
    if client is None:
        return
    try:
        client.delete(key)
    except Exception:
        _mark_unhealthy()


def group_summary_cache_key(group_id: str) -> str:
    return f"group_summary:{group_id}"


# ---------------------------------------------------------------------------
# Commit-bound invalidation
# ---------------------------------------------------------------------------
def invalidate_group_after_commit(db: Session, group_id: Any) -> None:
    """Register `group_id` for cache invalidation once `db` commits successfully."""
    db.info.setdefault(_INVALIDATION_KEY, set()).add(str(group_id))


def _pending(session: Session) -> Iterable[str]:
    return session.info.pop(_INVALIDATION_KEY, None) or ()


@event.listens_for(Session, "after_commit")
def _invalidate_on_commit(session: Session) -> None:
    for group_id in _pending(session):
        cache_delete(group_summary_cache_key(group_id))


@event.listens_for(Session, "after_rollback")
def _discard_on_rollback(session: Session) -> None:
    session.info.pop(_INVALIDATION_KEY, None)
