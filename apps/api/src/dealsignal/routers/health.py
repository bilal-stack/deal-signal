"""Liveness and readiness.

Readiness reports each dependency separately, so a failure names the part that is
down instead of returning a bare 500.
"""

from __future__ import annotations

from fastapi import APIRouter, Response, status
from sqlalchemy import text

from dealsignal import __version__
from dealsignal.core.deps import SessionDep, SettingsDep
from dealsignal.schemas.common import HealthStatus

router = APIRouter(tags=["health"])

OK = "ok"


@router.get("/health", response_model=HealthStatus)
async def health(settings: SettingsDep) -> HealthStatus:
    """The process is running. No dependencies are touched."""
    return HealthStatus(
        status=OK,
        version=__version__,
        environment=settings.environment,
        checks={},
    )


@router.get("/health/ready", response_model=HealthStatus)
async def ready(
    response: Response,
    settings: SettingsDep,
    session: SessionDep,
) -> HealthStatus:
    """The process can serve traffic: the database answers."""
    checks: dict[str, str] = {}
    try:
        await session.execute(text("SELECT 1"))
        checks["database"] = OK
    except Exception as exc:
        checks["database"] = f"unavailable: {exc.__class__.__name__}"

    healthy = all(value == OK for value in checks.values())
    if not healthy:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return HealthStatus(
        status=OK if healthy else "degraded",
        version=__version__,
        environment=settings.environment,
        checks=checks,
    )
