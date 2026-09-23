"""Response shapes shared across routers."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class ApiModel(BaseModel):
    """Base for every schema: reads ORM objects, rejects unknown fields."""

    model_config = ConfigDict(from_attributes=True, extra="forbid")


class HealthStatus(ApiModel):
    status: str
    version: str
    environment: str
    checks: dict[str, str]
