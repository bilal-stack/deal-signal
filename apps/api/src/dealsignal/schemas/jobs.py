"""Job requests and responses."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import Field

from dealsignal.models.enums import Country
from dealsignal.schemas.common import ApiModel
from dealsignal.sources.regions import REGIONS

MAX_SEED_LIMIT = 500
MAX_ENRICH_LIMIT = 200
DEFAULT_WEBSITE_READS = 5
MAX_WEBSITE_READS = 25

JobStatusName = Literal["queued", "in_progress", "complete", "failed", "not_found"]


class SeedRequest(ApiModel):
    region: Literal[tuple(sorted(REGIONS))]  # type: ignore[valid-type]
    industry: str = Field(min_length=1)
    limit: int = Field(default=200, ge=1, le=MAX_SEED_LIMIT)


class RegistryRequest(ApiModel):
    country: Country
    limit: int = Field(default=25, ge=1, le=MAX_ENRICH_LIMIT)


class EnrichRequest(ApiModel):
    limit: int = Field(default=50, ge=1, le=MAX_ENRICH_LIMIT)


class WebsiteReadRequest(ApiModel):
    """Each website read is one Claude call billed to the user's key, so batches are
    small by default and capped, whatever the client asks for."""

    limit: int = Field(default=DEFAULT_WEBSITE_READS, ge=1, le=MAX_WEBSITE_READS)


class JobStarted(ApiModel):
    id: str
    kind: str
    status: JobStatusName = "queued"


class JobState(ApiModel):
    """Where a job is. `result` is its report once it has finished."""

    id: str
    kind: str | None = None
    status: JobStatusName
    result: dict[str, Any] | None = None
    error: str | None = None
