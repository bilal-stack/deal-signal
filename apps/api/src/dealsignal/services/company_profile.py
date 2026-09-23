"""Everything we know about one company, gathered for the detail panel.

The panel answers three questions: what do we know, where did each part come from,
and why is the rest still missing. The enrichment attempts answer the last one.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from dealsignal.core.errors import NotFoundError
from dealsignal.models.company import Company
from dealsignal.models.enrichment import EnrichmentAttempt
from dealsignal.models.person import Person
from dealsignal.models.source import FieldValue
from dealsignal.repositories.company import CompanyRepository
from dealsignal.repositories.enrichment_attempt import EnrichmentAttemptRepository
from dealsignal.repositories.field_value import FieldValueRepository
from dealsignal.repositories.person import PersonRepository
from dealsignal.services.facts import best_by_field


@dataclass(frozen=True)
class CompanyProfile:
    company: Company
    people: list[Person]
    field_values: list[FieldValue]
    """Every answer from every source, for the provenance view."""
    best: dict[str, FieldValue]
    """The answer we trust most for each field."""
    attempts: list[EnrichmentAttempt]
    """The latest attempt per enrichment job, newest first."""


class CompanyProfileService:
    def __init__(self, session: AsyncSession) -> None:
        self._companies = CompanyRepository(session)
        self._people = PersonRepository(session)
        self._fields = FieldValueRepository(session)
        self._attempts = EnrichmentAttemptRepository(session)

    async def load(self, company_id: uuid.UUID) -> CompanyProfile:
        company = await self._companies.get(company_id)
        if company is None:
            raise NotFoundError(f"No company with id {company_id}.")

        values = await self._fields.all_for_company(company.id)
        return CompanyProfile(
            company=company,
            people=await self._people.for_company(company.id),
            field_values=values,
            best=best_by_field(values),
            attempts=await self._attempts.for_company(company.id),
        )
