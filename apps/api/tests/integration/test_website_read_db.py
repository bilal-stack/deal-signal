"""A recorded website read, stored and scored: the quotes must reach the score.

The reply is the real one recorded for A/C Service Co., replayed without a network.
"""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from dealsignal.ai.extractor import WebsiteExtractor
from dealsignal.core.config import Settings
from dealsignal.models.buy_box import BuyBox
from dealsignal.models.enums import BuyBoxMode, Country
from dealsignal.repositories.field_value import FieldValueRepository
from dealsignal.services.enrichment import WebsiteEnrichmentService
from dealsignal.services.scoring_service import ScoringService
from dealsignal.sources.website import WebsiteContent
from tests.claude_replay import ReplayedClaude
from tests.integration.factories import make_company

pytestmark = pytest.mark.integration

MAINTENANCE_QUOTE = "We offer commercial and residential preventative maintenance agreements."


class StubReader:
    """The pages we sent, as far as the replay cares: it answers the same either way."""

    async def read(self, url: str) -> WebsiteContent:
        return WebsiteContent(
            url=url,
            pages={
                url: (
                    "A/C Service Co. is a family owned and operated company serving Fort "
                    "Worth and Arlington since 1999. We offer commercial and residential "
                    "preventative maintenance agreements."
                )
            },
            last_copyright_year=2013,
        )


async def test_a_website_read_is_stored_and_quoted_in_the_score(db_session: AsyncSession) -> None:
    company = await make_company(
        db_session,
        display_name="A/C Service Co.",
        country=Country.US,
        website_url="http://checkmyac.com",
        industry_keys=["hvac"],
    )
    extractor = WebsiteExtractor(
        Settings(environment="ci"), client=ReplayedClaude("website_read").client
    )
    service = WebsiteEnrichmentService(db_session, StubReader(), extractor)  # type: ignore[arg-type]

    outcome = await service.enrich(company)

    assert outcome.succeeded
    assert company.founded_year == 1999
    assert company.summary is not None and "family owned" in company.summary
    [stored] = await FieldValueRepository(db_session).for_company(
        company.id, "has_recurring_revenue"
    )
    assert stored.evidence == MAINTENANCE_QUOTE

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

    reasons = {reason.key: reason for reason in scored.result.reasons}
    assert reasons["recurring_revenue"].evidence == MAINTENANCE_QUOTE
    assert reasons["family_ownership"].evidence is not None
    assert "family owned" in reasons["family_ownership"].evidence
