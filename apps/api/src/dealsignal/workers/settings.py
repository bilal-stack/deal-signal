"""arq worker configuration.

Jobs are registered here as they are built. Each one must be safe to run twice:
workers retry, and a retry must never double-charge or duplicate a record.
"""

from __future__ import annotations

from typing import Any, ClassVar

from arq.connections import RedisSettings

from dealsignal.core.config import get_settings
from dealsignal.core.logging import configure_logging, get_logger
from dealsignal.db.session import dispose_engine, init_engine
from dealsignal.workers.jobs import JOBS

log = get_logger(__name__)

MAX_TRIES = 1
"""No automatic retries: a job reports its own failures, and repeating a half-done
batch would only repeat them."""

JOB_TIMEOUT_SECONDS = 1800
KEEP_RESULTS_SECONDS = 24 * 60 * 60


async def startup(ctx: dict[str, Any]) -> None:
    settings = get_settings()
    configure_logging(settings)
    init_engine(settings)
    log.info("worker_started")


async def shutdown(ctx: dict[str, Any]) -> None:
    await dispose_engine()
    log.info("worker_stopped")


class WorkerSettings:
    """Entry point: `arq dealsignal.workers.settings.WorkerSettings`."""

    functions: ClassVar[list[Any]] = list(JOBS)
    on_startup = startup
    on_shutdown = shutdown
    max_tries = MAX_TRIES
    job_timeout = JOB_TIMEOUT_SECONDS
    keep_result = KEEP_RESULTS_SECONDS
    redis_settings = RedisSettings.from_dsn(str(get_settings().redis_url))
