"""Company endpoints: the results table and the detail panel."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Query

from dealsignal.core.deps import SessionDep
from dealsignal.models.company import Company
from dealsignal.models.enums import Country
from dealsignal.repositories.company import CompanyRepository
from dealsignal.schemas.company import (
    CompanyDetail,
    CompanySummary,
    EnrichmentCheck,
    FieldProvenance,
    PersonSummary,
)
from dealsignal.services.company_profile import CompanyProfileService
from dealsignal.services.domain_age import FIELD as DOMAIN_AGE_FIELD
from dealsignal.services.estimates import FIELD as REVENUE_ESTIMATE_FIELD

router = APIRouter(prefix="/companies", tags=["companies"])

DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 200
PART_OF_GROUP_FIELD = "is_part_of_group"


def _summary(company: Company) -> CompanySummary:
    return CompanySummary(
        id=company.id,
        name=company.display_name,
        city=company.city,
        region=company.region,
        country=str(company.country),
        domain=company.domain,
        phone=company.phone_e164,
        industry_label=company.industry_label,
        founded_year=company.founded_year,
    )


@router.get("", response_model=list[CompanySummary])
async def list_companies(
    session: SessionDep,
    country: Country | None = None,
    city: str | None = None,
    limit: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    offset: int = Query(default=0, ge=0),
) -> list[CompanySummary]:
    """Stored companies, before any Buy Box is applied."""
    repository = CompanyRepository(session)
    countries = [country] if country else list(Country)
    companies = await repository.search(countries=countries, city=city, limit=limit, offset=offset)
    return [_summary(company) for company in companies]


@router.get("/{company_id}", response_model=CompanyDetail)
async def get_company(company_id: uuid.UUID, session: SessionDep) -> CompanyDetail:
    """One company: what we know, where each part came from, and what is missing."""
    profile = await CompanyProfileService(session).load(company_id)
    company = profile.company
    revenue = profile.best.get(REVENUE_ESTIMATE_FIELD)
    registered = profile.best.get(DOMAIN_AGE_FIELD)
    group = profile.best.get(PART_OF_GROUP_FIELD)

    return CompanyDetail(
        **_summary(company).model_dump(),
        website_url=company.website_url,
        summary=company.summary,
        employee_count=company.employee_count,
        employee_band=company.employee_band,
        revenue_low=company.revenue_low,
        revenue_high=company.revenue_high,
        revenue_method=revenue.evidence if revenue else None,
        domain_registered_year=registered.value if registered else None,
        part_of_group=group.value if group else None,
        people=[
            PersonSummary(
                name=person.full_name,
                role=person.role,
                is_owner=person.is_owner,
                is_company=person.is_company,
                birth_year=person.birth_year,
                appointed_year=person.appointed_year,
                source=str(person.source),
            )
            for person in profile.people
        ],
        checks=[
            EnrichmentCheck(
                task=str(attempt.task),
                succeeded=attempt.succeeded,
                message=attempt.message,
                attempted_at=attempt.attempted_at,
            )
            for attempt in profile.attempts
        ],
        provenance=[
            FieldProvenance(
                field=value.field,
                value=value.value,
                source=str(value.source),
                confidence=value.confidence,
                evidence=value.evidence,
            )
            for value in profile.field_values
        ],
    )
