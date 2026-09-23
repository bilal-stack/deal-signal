"""Jobs must keep making progress when some companies can never be done."""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from dealsignal.models.enums import Country, EnrichmentTask, SourceName
from dealsignal.repositories.company import CompanyRepository
from dealsignal.repositories.enrichment_attempt import EnrichmentAttemptRepository
from dealsignal.services.domain_age import FIELD as DOMAIN_AGE_FIELD
from tests.integration.factories import add_field, add_person, make_company

pytestmark = pytest.mark.integration


async def test_companies_never_tried_come_before_ones_that_found_nothing(
    db_session: AsyncSession,
) -> None:
    """Companies never tried come first, so a job keeps making progress even when
    many of the rest can never be completed."""
    unpublished = [
        await make_company(db_session, display_name=f"A Unpublished {index}", domain=f"a{index}.uk")
        for index in range(3)
    ]
    untried = await make_company(db_session, display_name="Z Never Tried", domain="z.com")
    attempts = EnrichmentAttemptRepository(db_session)
    for company in unpublished:
        await attempts.record(
            company.id,
            EnrichmentTask.DOMAIN_AGE,
            succeeded=False,
            message="The registry does not publish a date.",
        )

    picked = await CompanyRepository(db_session).needing_field(
        DOMAIN_AGE_FIELD, task=EnrichmentTask.DOMAIN_AGE, limit=1, require_domain=True
    )

    assert [company.display_name for company in picked] == ["Z Never Tried"]
    assert untried in picked


async def test_the_oldest_attempt_is_retried_first(db_session: AsyncSession) -> None:
    repository = CompanyRepository(db_session)
    attempts = EnrichmentAttemptRepository(db_session)
    first = await make_company(db_session, display_name="Tried First", country=Country.FR)
    second = await make_company(db_session, display_name="Tried Second", country=Country.FR)
    for company in (first, second):
        await attempts.record(
            company.id, EnrichmentTask.REGISTRY, succeeded=False, message="No match."
        )

    picked = await repository.needing_register_lookup(Country.FR, limit=2)

    assert [company.display_name for company in picked] == ["Tried First", "Tried Second"]


async def test_a_new_attempt_replaces_the_old_one(db_session: AsyncSession) -> None:
    company = await make_company(db_session, display_name="Retried Co", website_url="https://r.co")
    attempts = EnrichmentAttemptRepository(db_session)

    await attempts.record(
        company.id, EnrichmentTask.WEBSITE, succeeded=False, message="The site timed out."
    )
    await attempts.record(
        company.id, EnrichmentTask.WEBSITE, succeeded=True, message="Read 3 pages."
    )

    recorded = await attempts.for_company(company.id)
    assert [(item.succeeded, item.message) for item in recorded] == [(True, "Read 3 pages.")]


async def test_the_company_panel_says_what_we_know_and_what_we_tried(
    db_session: AsyncSession, api: AsyncClient
) -> None:
    company = await make_company(
        db_session,
        display_name="Lyon Chauffage",
        country=Country.FR,
        employee_band="10-19",
        revenue_low=1_500_000,
        revenue_high=2_500_000,
    )
    await add_field(
        db_session,
        company,
        "revenue_estimate",
        {"low": 1_500_000, "high": 2_500_000},
        source=SourceName.ESTIMATE,
        evidence="15 staff x $100k-$167k revenue per employee (rule of thumb)",
    )
    await add_field(db_session, company, DOMAIN_AGE_FIELD, 2004, source=SourceName.RDAP)
    await add_person(db_session, company, "Marie Durand", is_owner=True, birth_year=1961)
    await EnrichmentAttemptRepository(db_session).record(
        company.id,
        EnrichmentTask.WEBSITE,
        succeeded=False,
        message="The website had no readable text on it.",
    )

    response = await api.get(f"/companies/{company.id}")

    assert response.status_code == 200
    body = response.json()
    assert body["employee_band"] == "10-19"
    assert (body["revenue_low"], body["revenue_high"]) == (1_500_000, 2_500_000)
    assert body["revenue_method"].startswith("15 staff x"), "an estimate shows its arithmetic"
    assert body["domain_registered_year"] == 2004
    assert body["people"][0]["name"] == "Marie Durand"
    assert body["people"][0]["birth_year"] == 1961
    assert body["checks"] == [
        {
            "task": "website",
            "succeeded": False,
            "message": "The website had no readable text on it.",
            "attempted_at": body["checks"][0]["attempted_at"],
        }
    ]
    recorded = {entry["field"]: entry["value"] for entry in body["provenance"]}
    assert recorded["revenue_estimate"] == {"low": 1_500_000, "high": 2_500_000}
