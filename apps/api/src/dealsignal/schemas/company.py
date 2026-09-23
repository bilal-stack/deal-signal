"""Company and score responses.

A score never travels without its reasons, and an unknown field says so rather
than arriving as an empty string.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import Field

from dealsignal.schemas.common import ApiModel


class ScoreReason(ApiModel):
    key: str
    points: float
    max_points: int
    reason: str
    evidence: str | None = None


class FieldProvenance(ApiModel):
    """One source's answer for one field, and how far we trust it."""

    field: str
    value: Any
    source: str
    confidence: float
    evidence: str | None = None


class PersonSummary(ApiModel):
    """Someone the register lists: an owner, a director, or a holding company."""

    name: str
    role: str | None
    is_owner: bool
    is_company: bool
    birth_year: int | None
    appointed_year: int | None
    source: str


class EnrichmentCheck(ApiModel):
    """The latest attempt at one enrichment, so an empty field explains itself."""

    task: str
    succeeded: bool
    message: str
    attempted_at: datetime


class CompanySummary(ApiModel):
    """One row of the results table."""

    id: uuid.UUID
    name: str
    city: str | None
    region: str | None
    country: str
    domain: str | None
    phone: str | None
    industry_label: str | None
    founded_year: int | None

    score: float | None = None
    confidence: float | None = None
    confidence_label: str | None = None
    reasons: list[ScoreReason] = Field(default_factory=list)


class CompanyDetail(CompanySummary):
    """The side panel: everything we know, and where each part came from."""

    website_url: str | None = None
    summary: str | None = None
    employee_count: int | None = None
    employee_band: str | None = None
    """What a register publishes instead of a count, such as "10-19"."""
    revenue_low: int | None = None
    revenue_high: int | None = None
    revenue_method: str | None = None
    """How the revenue range was estimated. Always shown with it: it is our figure."""
    domain_registered_year: int | None = None
    part_of_group: bool | None = None
    people: list[PersonSummary] = Field(default_factory=list)
    checks: list[EnrichmentCheck] = Field(default_factory=list)
    provenance: list[FieldProvenance] = Field(default_factory=list)
    missing_signals: list[str] = Field(default_factory=list)
    """Named so the UI can say why confidence is low instead of showing a bare N/A."""
