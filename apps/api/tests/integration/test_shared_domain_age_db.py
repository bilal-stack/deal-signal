"""A domain several businesses list dates none of them."""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from dealsignal.models.buy_box import BuyBox
from dealsignal.models.enums import BuyBoxMode, SourceName
from dealsignal.services.domain_age import FIELD, DomainAgeService
from dealsignal.services.scoring_service import ScoringService
from dealsignal.sources.rdap import DomainRegistration
from tests.integration.factories import add_field, make_company

pytestmark = pytest.mark.integration


class UnusedRegistry:
    """Fails the test if a lookup is made: none should be."""

    async def lookup(self, domain: str) -> DomainRegistration:
        raise AssertionError(f"looked up {domain}")


async def test_a_domain_two_businesses_list_is_not_looked_up(db_session: AsyncSession) -> None:
    first = await make_company(
        db_session, display_name="Comfort Pros of Fort Worth", domain="comfortpros.com"
    )
    await make_company(
        db_session, display_name="Comfort Pros of Sugar Land", domain="comfortpros.com"
    )

    outcome = await DomainAgeService(db_session, UnusedRegistry()).enrich(first)  # type: ignore[arg-type]

    assert outcome.succeeded is False
    assert outcome.message == (
        "Several businesses list comfortpros.com, so its age says nothing about this one."
    )


async def test_a_date_for_a_shared_domain_does_not_count_as_years_in_business(
    db_session: AsyncSession,
) -> None:
    """A date recorded before the domain turned out to be shared must not score."""
    company = await make_company(
        db_session, display_name="Comfort Pros of Fort Worth", domain="comfortpros.com"
    )
    await make_company(
        db_session, display_name="Comfort Pros of Sugar Land", domain="comfortpros.com"
    )
    await add_field(db_session, company, FIELD, 1996, source=SourceName.RDAP)
    buy_box = BuyBox(
        name="HVAC to buy",
        industries=["hvac"],
        countries=["US"],
        weights={},
        mode=BuyBoxMode.ACQUISITION,
    )
    db_session.add(buy_box)
    await db_session.flush()

    scored = await ScoringService(db_session).score_company(company, buy_box)

    assert "years_in_business" not in {reason.key for reason in scored.result.reasons}
