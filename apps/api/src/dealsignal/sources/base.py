"""What every data source must look like.

One class per source, all with the same shape, so adding a source never touches
the services that use them. A source returns plain records, never ORM objects, and
raises `ExternalServiceError` (or `SourceBlockedError`) when it cannot answer.
It must never return an empty result to hide a failure.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date

from pydantic import BaseModel, ConfigDict, Field

from dealsignal.models.enums import Country, SourceName
from dealsignal.sources.industries import Industry
from dealsignal.sources.regions import Region


class PlaceRecord(BaseModel):
    """A business as a discovery source describes it."""

    model_config = ConfigDict(frozen=True)

    source: SourceName
    external_id: str
    name: str
    country: Country
    category: str | None = None
    street: str | None = None
    city: str | None = None
    region: str | None = None
    postal_code: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    website: str | None = None
    phone: str | None = None
    review_count: int | None = None
    raw: dict[str, object] = Field(default_factory=dict)


class OfficerRecord(BaseModel):
    """A director or owner from an official register.

    Registers list companies as directors too. A holding company cannot be phoned
    or retire, so it is flagged rather than treated as a person: it tells us the
    business has a parent, which makes it less likely to be for sale.
    """

    model_config = ConfigDict(frozen=True)

    full_name: str
    role: str | None = None
    birth_year: int | None = None
    appointed_on: date | None = None
    is_owner: bool = False
    is_company: bool = False


class RegistryRecord(BaseModel):
    """A company as an official register describes it."""

    model_config = ConfigDict(frozen=True)

    source: SourceName
    registry_id: str
    legal_name: str
    country: Country
    incorporated_on: date | None = None
    industry_code: str | None = None
    status: str | None = None
    employee_band: str | None = None
    parent_name: str | None = None
    officers: tuple[OfficerRecord, ...] = ()
    raw: dict[str, object] = Field(default_factory=dict)


class DataSource(ABC):
    """Shared identity and availability check for every source."""

    name: SourceName
    countries: frozenset[Country]

    def covers(self, country: Country) -> bool:
        return country in self.countries

    @abstractmethod
    async def is_available(self) -> bool:
        """False when a key is missing or the service is switched off.

        Callers skip an unavailable source and say so, rather than failing the search.
        """


class PlaceSource(DataSource):
    """Finds businesses by industry and area."""

    @abstractmethod
    async def search(self, *, industry: Industry, region: Region, limit: int) -> list[PlaceRecord]:
        """Return businesses matching the request.

        Raise on failure. An empty list means "we looked and there are none", so it
        must never be used to hide an error.
        """


class RegistrySource(DataSource):
    """Looks up a company in an official register."""

    @abstractmethod
    async def lookup(
        self, *, name: str, country: Country, city: str | None = None
    ) -> RegistryRecord | None:
        """Return the register entry, or None when there is genuinely no match."""
