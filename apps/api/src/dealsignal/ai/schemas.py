"""What we ask Claude to extract from a company website.

Every field is optional and every fact carries the sentence it came from. A model
that cannot find a fact returns null, which flows through to "unknown" in the UI
and to a lower confidence in the score. Nothing here is allowed to be a guess.

The schema is sent as a structured-output format, which supports a subset of JSON
Schema: every object is closed, so evidence is a list of (fact, quote) pairs rather
than a map, and range limits are enforced here rather than by the API. A value
outside its range becomes unknown instead of discarding the whole read.
"""

from __future__ import annotations

from datetime import date
from typing import Literal, get_args

from pydantic import BaseModel, ConfigDict, Field, field_validator

MAX_EVIDENCE_CHARS = 200
MIN_PLAUSIBLE_FOUNDING_YEAR = 1800
ELLIPSIS = "\u2026"

FactName = Literal[
    "founded_year",
    "owner_name",
    "mentions_family_ownership",
    "location_count",
    "employee_count",
    "sells_to_businesses",
    "has_recurring_revenue",
    "is_part_of_group",
]
FACT_NAMES: tuple[str, ...] = get_args(FactName)


class Evidence(BaseModel):
    """A fact and the words on the page that support it."""

    model_config = ConfigDict(frozen=True)

    fact: FactName = Field(description="The field this sentence supports.")
    quote: str = Field(
        description=(
            f"The sentence from the page, copied word for word, under {MAX_EVIDENCE_CHARS} "
            "characters."
        )
    )

    @field_validator("quote", mode="before")
    @classmethod
    def _shorten(cls, value: object) -> object:
        """A long sentence is shortened, not refused: its start is still verbatim."""
        if isinstance(value, str) and len(value) > MAX_EVIDENCE_CHARS:
            return value[: MAX_EVIDENCE_CHARS - 1].rstrip() + ELLIPSIS
        return value


class WebsiteFacts(BaseModel):
    """The facts a buyer cares about, as found on the company's own site."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    summary: str = Field(
        description="One or two plain sentences on what this business does and for whom."
    )
    services: list[str] = Field(
        default_factory=list,
        description="The services or products offered, in the site's own words.",
    )

    founded_year: int | None = Field(
        default=None,
        description=(
            "The four-digit year the business started, only if the site states it, "
            "for example 'serving Dallas since 1996'."
        ),
    )
    owner_name: str | None = Field(
        default=None, description="The owner or founder, only if the site names them."
    )
    mentions_family_ownership: bool | None = Field(
        default=None, description="True only if the site describes itself as family owned or run."
    )
    location_count: int | None = Field(
        default=None, description="Number of locations, only if the site lists them."
    )
    employee_count: int | None = Field(
        default=None,
        description=(
            "Team size, only if the site states a number, for example 'our team of 25' "
            "or a staff page you can count. Never estimate it from how big the site feels."
        ),
    )

    sells_to_businesses: bool | None = Field(
        default=None, description="True if it serves commercial or trade customers."
    )
    has_recurring_revenue: bool | None = Field(
        default=None,
        description="True only for stated maintenance contracts, service plans or subscriptions.",
    )
    is_part_of_group: bool | None = Field(
        default=None, description="True if the site says it belongs to a parent company or group."
    )

    opening_line: str | None = Field(
        default=None,
        description=(
            "One specific, respectful sentence a buyer could open with, built from a real "
            "detail on the site. No flattery, no sales language."
        ),
    )

    evidence: list[Evidence] = Field(
        default_factory=list,
        description="One entry for each fact you filled in, with its sentence from the page.",
    )

    @field_validator("founded_year", mode="before")
    @classmethod
    def _plausible_year(cls, value: object) -> object:
        """A year before 1800 or in the future is a misread, so it is unknown."""
        if isinstance(value, int) and not (
            MIN_PLAUSIBLE_FOUNDING_YEAR <= value <= date.today().year
        ):
            return None
        return value

    @field_validator("location_count", "employee_count", mode="before")
    @classmethod
    def _positive_count(cls, value: object) -> object:
        """Zero or fewer is not a count anyone stated, so it is unknown."""
        if isinstance(value, int) and value < 1:
            return None
        return value

    def known_fields(self) -> dict[str, object]:
        """Only the facts that were actually found, for merging into a company."""
        return {name: value for name in FACT_NAMES if (value := getattr(self, name)) is not None}

    def quote_for(self, fact: str) -> str | None:
        """The sentence behind one fact, if the reader gave one."""
        return next((item.quote for item in self.evidence if item.fact == fact), None)
