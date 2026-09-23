"""Attaching official register data to a company.

This is where the strongest signal in the product comes from: a director's year
of birth. Only the UK and France publish it, so this service says plainly when a
country has no register we can use, rather than leaving the field quietly empty.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from dealsignal.core.errors import ExternalServiceError
from dealsignal.core.logging import get_logger
from dealsignal.matching.merge import confidence_of
from dealsignal.models.company import Company
from dealsignal.models.enums import Country, EmployeeBand
from dealsignal.models.person import Person
from dealsignal.repositories.field_value import FieldValueRepository
from dealsignal.repositories.person import PersonRepository
from dealsignal.services.estimates import record_revenue_estimate
from dealsignal.sources.base import RegistryRecord, RegistrySource

log = get_logger(__name__)

NO_REGISTER_MESSAGE = (
    "No free public register covers {country}, so company age and owner details "
    "have to come from the website instead."
)


class RegistryOutcome(BaseModel):
    """What the register gave us, or why it gave us nothing."""

    model_config = ConfigDict(frozen=True)

    company_id: str
    succeeded: bool
    message: str
    registry_id: str | None = None
    owners_found: int = 0
    owner_birth_years: list[int] = []


class RegistryEnrichmentService:
    """Looks a company up in whichever register covers its country."""

    def __init__(self, session: AsyncSession, sources: Sequence[RegistrySource]) -> None:
        self._session = session
        self._sources = tuple(sources)
        self._fields = FieldValueRepository(session)
        self._people = PersonRepository(session)

    def source_for(self, country: Country) -> RegistrySource | None:
        return next((source for source in self._sources if source.covers(country)), None)

    async def enrich(self, company: Company) -> RegistryOutcome:
        country = Country(company.country)
        source = self.source_for(country)
        if source is None:
            return self._failure(company, NO_REGISTER_MESSAGE.format(country=country))

        try:
            record = await source.lookup(
                name=company.display_name, country=country, city=company.city
            )
        except ExternalServiceError as error:
            return self._failure(company, error.message)

        if record is None:
            return self._failure(company, "No match for this company in the register.")

        await self._store(company, record)
        birth_years = [
            officer.birth_year for officer in record.officers if officer.birth_year is not None
        ]
        owners = sum(1 for officer in record.officers if officer.is_owner)

        log.info(
            "registry_enriched",
            company=company.display_name,
            registry_id=record.registry_id,
            owners=owners,
        )
        return RegistryOutcome(
            company_id=str(company.id),
            succeeded=True,
            message=f"Matched {record.legal_name} in the register.",
            registry_id=record.registry_id,
            owners_found=owners,
            owner_birth_years=birth_years,
        )

    async def _store(self, company: Company, record: RegistryRecord) -> None:
        """Write the register's facts, which outrank anything scraped."""
        observed_at = datetime.now(UTC)
        confidence = confidence_of(record.source)

        company.legal_name = record.legal_name
        if record.incorporated_on is not None:
            company.founded_year = record.incorporated_on.year
            await self._fields.record(
                company_id=company.id,
                field="founded_year",
                value=record.incorporated_on.year,
                source=record.source,
                observed_at=observed_at,
                confidence=confidence,
                evidence=(
                    f"Incorporated {record.incorporated_on.isoformat()} "
                    f"(register id {record.registry_id})"
                ),
            )

        if record.employee_band:
            company.employee_band = EmployeeBand(record.employee_band)
            await self._fields.record(
                company_id=company.id,
                field="employee_band",
                value=record.employee_band,
                source=record.source,
                observed_at=observed_at,
                confidence=confidence,
                evidence=f"Headcount band published by the register: {record.employee_band}",
            )

        corporate = [officer for officer in record.officers if officer.is_company]
        if corporate:
            await self._fields.record(
                company_id=company.id,
                field="is_part_of_group",
                value=True,
                source=record.source,
                observed_at=observed_at,
                confidence=confidence,
                evidence=(f"The register lists a company as a director: {corporate[0].full_name}"),
            )

        if record.parent_name:
            await self._fields.record(
                company_id=company.id,
                field="is_part_of_group",
                value=True,
                source=record.source,
                observed_at=observed_at,
                confidence=confidence,
                evidence=f"Register lists a parent: {record.parent_name}",
            )

        await record_revenue_estimate(company, self._fields, observed_at=observed_at)

        for officer in record.officers:
            await self._people.upsert_by_name(
                Person(
                    company_id=company.id,
                    full_name=officer.full_name,
                    role=officer.role,
                    is_owner=officer.is_owner,
                    is_company=officer.is_company,
                    birth_year=officer.birth_year,
                    appointed_year=officer.appointed_on.year if officer.appointed_on else None,
                    source=record.source,
                )
            )

    @staticmethod
    def _failure(company: Company, message: str) -> RegistryOutcome:
        log.info("registry_skipped", company=company.display_name, reason=message)
        return RegistryOutcome(company_id=str(company.id), succeeded=False, message=message)
