"""The connection the API uses to hand work to the worker.

If Redis is unreachable the API still starts: searching and browsing do not need
it. Starting a job then fails with a clear message instead of the whole app
refusing to boot.
"""

from __future__ import annotations

from arq import create_pool
from arq.connections import ArqRedis, RedisSettings
from redis.exceptions import RedisError

from dealsignal.core.config import Settings
from dealsignal.core.logging import get_logger

log = get_logger(__name__)


STARTUP_CONNECTION_ATTEMPTS = 2
STARTUP_RETRY_DELAY_SECONDS = 1


async def open_queue(settings: Settings) -> ArqRedis | None:
    redis_settings = RedisSettings.from_dsn(str(settings.redis_url))
    # A short retry budget: waiting half a minute for Redis would hold up the whole
    # API, when everything except starting a job works without it.
    redis_settings.conn_retries = STARTUP_CONNECTION_ATTEMPTS
    redis_settings.conn_retry_delay = STARTUP_RETRY_DELAY_SECONDS
    try:
        return await create_pool(redis_settings)
    except (RedisError, OSError) as exc:  # redis raises its own ConnectionError type
        log.warning("job_queue_unavailable", error=str(exc))
        return None


async def close_queue(queue: ArqRedis | None) -> None:
    if queue is not None:
        await queue.aclose()
