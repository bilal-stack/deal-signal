"""Buy Box requests and responses."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import Field, model_validator

from dealsignal.models.enums import BuyBoxMode, Country
from dealsignal.schemas.common import ApiModel

MAX_RADIUS_KM = 500
DEFAULT_RADIUS_KM = 50


class BuyBoxCreate(ApiModel):
    """What the user fills in once, then reuses for every search."""

    name: str = Field(min_length=1, max_length=120)
    mode: BuyBoxMode = Field(
        default=BuyBoxMode.ACQUISITION,
        description="acquisition: owners who may sell. sales: companies likely to buy from you.",
    )
    industries: list[str] = Field(min_length=1, description="For example: hvac, plumbing")
    countries: list[Country] = Field(min_length=1)
    city: str | None = None
    region: str | None = None
    radius_km: int = Field(default=DEFAULT_RADIUS_KM, ge=1, le=MAX_RADIUS_KM)

    revenue_min: int | None = Field(default=None, ge=0)
    revenue_max: int | None = Field(default=None, ge=0)
    employees_min: int | None = Field(default=None, ge=0)
    employees_max: int | None = Field(default=None, ge=0)
    exclude_pe_owned: bool = True
    weights: dict[str, int] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _ranges_must_make_sense(self) -> BuyBoxCreate:
        """Catch a reversed range here, where we can say so plainly."""
        revenue = (self.revenue_min, self.revenue_max)
        if None not in revenue and self.revenue_min > self.revenue_max:  # type: ignore[operator]
            raise ValueError("The lowest revenue cannot be above the highest.")

        employees = (self.employees_min, self.employees_max)
        if None not in employees and self.employees_min > self.employees_max:  # type: ignore[operator]
            raise ValueError("The smallest headcount cannot be above the largest.")
        return self


class BuyBoxRead(ApiModel):
    id: uuid.UUID
    name: str
    mode: BuyBoxMode
    industries: list[str]
    countries: list[str]
    city: str | None
    region: str | None
    radius_km: int
    revenue_min: int | None
    revenue_max: int | None
    employees_min: int | None
    employees_max: int | None
    exclude_pe_owned: bool
    weights: dict[str, int]
    created_at: datetime
