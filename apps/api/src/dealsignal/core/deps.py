"""Shared FastAPI dependencies.

Routes take settings from the application they belong to, not from a module-level
cache. That is what lets a test build an app with its own settings and have the
routes actually see them.
"""

from __future__ import annotations

from typing import Annotated

from arq.connections import ArqRedis
from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from dealsignal.core.config import Settings
from dealsignal.core.errors import ExternalServiceError
from dealsignal.db.session import get_session


def app_settings(request: Request) -> Settings:
    """The settings this application was created with."""
    return request.app.state.settings  # type: ignore[no-any-return]


SettingsDep = Annotated[Settings, Depends(app_settings)]
SessionDep = Annotated[AsyncSession, Depends(get_session)]


def job_queue(request: Request) -> ArqRedis:
    """The background job queue, or a clear error when it is not running."""
    queue: ArqRedis | None = getattr(request.app.state, "jobs", None)
    if queue is None:
        raise ExternalServiceError(
            "The background job queue is not running, so this cannot start. "
            "Check that the redis and worker services are up.",
            source="job_queue",
            retryable=True,
        )
    return queue


JobQueueDep = Annotated[ArqRedis, Depends(job_queue)]
