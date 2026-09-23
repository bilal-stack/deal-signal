"""The facts a signal is allowed to see.

Scoring never touches the database or the ORM. A builder turns a Company row into
this plain object, so every signal is a pure function of known facts and can be
tested with a two-line fixture.

`None` always means "we do not know", never "zero".
"""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, ConfigDict, Field


class CompanyFacts(BaseModel):
    """Everything known about one company at scoring time."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    country: str
    industry_code: str | None = None
    industry_label: str | None = None

    founded_year: int | None = None
    domain_registered_year: int | None = None
    """When the website domain was registered. Proves a minimum age, never youth."""
    owner_birth_year: int | None = None

    employee_count: int | None = None
    revenue_low: int | None = None
    revenue_high: int | None = None

    has_parent_company: bool | None = None
    has_named_contact: bool | None = None
    """True when a real person, not a holding company, is on record."""
    is_private_equity_owned: bool | None = None
    location_count: int | None = None

    has_recurring_revenue: bool | None = None
    sells_to_businesses: bool | None = None
    mentions_family_ownership: bool | None = None

    website_last_updated_year: int | None = None
    review_count: int | None = None
    review_growth_ratio: float | None = None
    """New reviews this year divided by last year. Below 1.0 means slowing down."""

    evidence: dict[str, str] = Field(default_factory=dict)
    """field name -> short quote, so a reason can show where it came from."""


class BuyBoxCriteria(BaseModel):
    """What the user asked for. Industry and country are filtered before scoring."""

    model_config = ConfigDict(frozen=True)

    revenue_min: int | None = None
    revenue_max: int | None = None
    employees_min: int | None = None
    employees_max: int | None = None
    exclude_pe_owned: bool = True
    weights: dict[str, int] = Field(default_factory=dict)


class ScoringContext(BaseModel):
    """One company, one Buy Box, one reference date."""

    model_config = ConfigDict(frozen=True)

    facts: CompanyFacts
    criteria: BuyBoxCriteria
    today: date = Field(default_factory=date.today)

    @property
    def current_year(self) -> int:
        return self.today.year
