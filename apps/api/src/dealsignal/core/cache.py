"""Pacing outside requests, and remembering their answers.

Two jobs, one interface:

* **Rate limiting.** One request per domain per second, counted across every
  process. The API and the worker can both be crawling, so an in-process pause is
  not enough to keep a promise made to someone else's server.
* **Caching.** Registry and domain lookups barely change. Re-asking wastes their
  capacity and our time, and repeats a request we already made.

When Redis is not available the same interface runs in-process: pacing still works
inside one process, and the cache is a plain dictionary. Nothing has to branch on
which one it got.
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any, Protocol

from redis.asyncio import Redis
from redis.exceptions import RedisError

from dealsignal.core.config import Settings
from dealsignal.core.logging import get_logger

log = get_logger(__name__)

MINIMUM_WAIT_SECONDS = 0.01
RATE_LIMIT_PREFIX = "crawl"


class Cache(Protocol):
    """What sources need: wait your turn, and remember the answer."""

    async def wait_for_turn(self, key: str, min_interval_seconds: float) -> None: ...

    async def get(self, key: str) -> Any | None: ...

    async def set(self, key: str, value: Any, ttl_seconds: int) -> None: ...

    async def close(self) -> None: ...


class LocalCache:
    """In-process fallback. Correct for one process, which is better than nothing."""

    def __init__(self) -> None:
        self._next_allowed: dict[str, float] = {}
        self._values: dict[str, tuple[float, Any]] = {}

    async def wait_for_turn(self, key: str, min_interval_seconds: float) -> None:
        now = time.monotonic()
        earliest = self._next_allowed.get(key, now)
        if earliest > now:
            await asyncio.sleep(earliest - now)
        self._next_allowed[key] = max(earliest, now) + min_interval_seconds

    async def get(self, key: str) -> Any | None:
        entry = self._values.get(key)
        if entry is None:
            return None
        expires_at, value = entry
        if expires_at < time.monotonic():
            del self._values[key]
            return None
        return value

    async def set(self, key: str, value: Any, ttl_seconds: int) -> None:
        self._values[key] = (time.monotonic() + ttl_seconds, value)

    async def close(self) -> None:
        return None


class RedisCache:
    """Shared across processes, so one server sees one request per interval."""

    def __init__(self, redis: Redis) -> None:
        self._redis = redis

    async def wait_for_turn(self, key: str, min_interval_seconds: float) -> None:
        """Hold a short-lived lock per key; wait for whoever has it."""
        interval_ms = max(int(min_interval_seconds * 1000), 1)
        lock = f"{RATE_LIMIT_PREFIX}:{key}"
        while True:
            try:
                if await self._redis.set(lock, "1", nx=True, px=interval_ms):
                    return
                remaining_ms = await self._redis.pttl(lock)
            except RedisError as exc:
                log.warning("rate_limit_unavailable", error=str(exc))
                return
            await asyncio.sleep(max(remaining_ms, 1) / 1000 + MINIMUM_WAIT_SECONDS)

    async def get(self, key: str) -> Any | None:
        try:
            raw = await self._redis.get(key)
        except RedisError:
            return None
        return json.loads(raw) if raw else None

    async def set(self, key: str, value: Any, ttl_seconds: int) -> None:
        try:
            await self._redis.set(key, json.dumps(value), ex=ttl_seconds)
        except RedisError as exc:
            log.warning("cache_write_failed", key=key, error=str(exc))

    async def close(self) -> None:
        await self._redis.aclose()


async def open_cache(settings: Settings) -> Cache:
    """A shared cache when Redis answers, an in-process one when it does not."""
    redis: Redis = Redis.from_url(str(settings.redis_url), decode_responses=True)
    try:
        await redis.ping()
    except (RedisError, OSError) as exc:
        log.warning("cache_local_only", error=str(exc))
        await redis.aclose()
        return LocalCache()
    return RedisCache(redis)
