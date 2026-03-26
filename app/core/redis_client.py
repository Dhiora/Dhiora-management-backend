"""Async Redis client with graceful degradation.

Cache failures are silently swallowed so the API continues to work
even when Redis is unavailable.
"""

import json
import logging
from typing import Any, Optional

import redis.asyncio as aioredis

from app.core.config import settings

logger = logging.getLogger(__name__)

_redis: Optional[aioredis.Redis] = None


def get_redis() -> aioredis.Redis:
    """Return (or lazily create) the async Redis connection pool."""
    global _redis
    if _redis is None:
        _redis = aioredis.from_url(
            settings.redis_url,
            encoding="utf-8",
            decode_responses=True,
            socket_connect_timeout=2,
            socket_timeout=2,
        )
    return _redis


async def cache_get(key: str) -> Optional[Any]:
    """Return the decoded JSON value for *key*, or None on miss / error."""
    try:
        r = get_redis()
        raw = await r.get(key)
        return json.loads(raw) if raw is not None else None
    except Exception as exc:
        logger.debug("Redis cache_get failed for key=%s: %s", key, exc)
        return None


async def cache_set(key: str, value: Any, ttl: int = 300) -> None:
    """Serialise *value* to JSON and store it in Redis with *ttl* seconds TTL."""
    try:
        r = get_redis()
        await r.set(key, json.dumps(value, default=str), ex=ttl)
    except Exception as exc:
        logger.debug("Redis cache_set failed for key=%s: %s", key, exc)


async def cache_delete(key: str) -> None:
    """Delete *key* from Redis (best-effort)."""
    try:
        r = get_redis()
        await r.delete(key)
    except Exception as exc:
        logger.debug("Redis cache_delete failed for key=%s: %s", key, exc)


async def cache_delete_pattern(pattern: str) -> None:
    """Delete all keys matching *pattern* (SCAN-based, safe for production)."""
    try:
        r = get_redis()
        async for key in r.scan_iter(pattern):
            await r.delete(key)
    except Exception as exc:
        logger.debug("Redis cache_delete_pattern failed for pattern=%s: %s", pattern, exc)
