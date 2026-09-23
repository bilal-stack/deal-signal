"""The do-not-contact list, and what it stops.

An entry here is someone asking not to be approached. If it ever fails quietly,
the tool does the one thing it must never do, so these run against a real database.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from dealsignal.ai.outreach import OutreachDraft
from dealsignal.models.buy_box import BuyBox
from dealsignal.models.enums import SourceName, SuppressionKind
from dealsignal.repositories.suppression import SuppressionRepository
from dealsignal.services.outreach import OutreachService, SenderProfile
from dealsignal.services.search import SearchService
from dealsignal.services.suppression import SuppressionService
from tests.integration.factories import add_field, add_person, make_company

pytestmark = pytest.mark.integration


async def hvac_buy_box(session: AsyncSession) -> BuyBox:
    buy_box = BuyBox(name="HVAC", industries=["hvac"], countries=["US"], weights={})
    session.add(buy_box)
    await session.flush()
    return buy_box


async def test_a_blocked_company_never_reaches_the_results(
    api: AsyncClient, db_session: AsyncSession
) -> None:
    keep = await make_company(db_session, display_name="Contactable Air", industry_keys=["hvac"])
    blocked = await make_company(
        db_session, display_name="Asked Us To Stop", industry_keys=["hvac"]
    )
    await SuppressionRepository(db_session).block(
        kind=SuppressionKind.COMPANY, value=str(blocked.id), reason="Asked not to be contacted"
    )
    buy_box = await hvac_buy_box(db_session)

    outcome = await SearchService(db_session).run(buy_box)

    names = {item.name for item in outcome.scored}
    assert keep.display_name in names
    assert blocked.display_name not in names
    assert outcome.withheld == 1


async def test_a_blocked_company_is_left_out_of_the_export(
    api: AsyncClient, db_session: AsyncSession
) -> None:
    await make_company(db_session, display_name="Contactable Air", industry_keys=["hvac"])
    blocked = await make_company(
        db_session, display_name="Asked Us To Stop", industry_keys=["hvac"]
    )
    await SuppressionRepository(db_session).block(
        kind=SuppressionKind.COMPANY, value=str(blocked.id), reason=None
    )
    buy_box = await hvac_buy_box(db_session)

    body = (await api.get(f"/buy-boxes/{buy_box.id}/export?format=csv")).text

    assert "Contactable Air" in body
    assert "Asked Us To Stop" not in body


async def test_blocking_a_domain_covers_the_company_that_uses_it(
    db_session: AsyncSession,
) -> None:
    company = await make_company(
        db_session, display_name="Domain Blocked Co", domain="blocked.com", industry_keys=["hvac"]
    )
    await SuppressionService(db_session).block(SuppressionKind.DOMAIN, "BLOCKED.com", "Competitor")

    match = await SuppressionRepository(db_session).matching(company)

    assert match is not None
    assert match.reason == "Competitor"


async def test_blocking_the_same_thing_twice_is_not_an_error(
    api: AsyncClient, db_session: AsyncSession
) -> None:
    company = await make_company(db_session, display_name="Twice Blocked")
    payload = {"kind": "company", "value": str(company.id), "reason": "Already a client"}

    first = await api.post("/suppression", json=payload)
    second = await api.post("/suppression", json=payload)

    assert first.status_code == 201
    assert second.status_code == 201
    assert len((await api.get("/suppression")).json()) == 1


async def test_a_draft_is_refused_for_a_blocked_company(
    api: AsyncClient, db_session: AsyncSession
) -> None:
    """Refused before any model call: the point is not to write to them at all."""
    company = await make_company(db_session, display_name="Asked Us To Stop")
    await api.post(
        "/suppression",
        json={"kind": "company", "value": str(company.id), "reason": "Asked not to be contacted"},
    )

    response = await api.post(
        "/outreach/drafts",
        json={
            "company_id": str(company.id),
            "sender": {"name": "Bilal", "background": "Looking to buy an HVAC business."},
        },
    )

    assert response.status_code == 409
    assert "do-not-contact list" in response.json()["error"]["message"]


async def test_removing_an_entry_lets_the_company_back_in(
    api: AsyncClient, db_session: AsyncSession
) -> None:
    company = await make_company(db_session, display_name="Unblocked Later", industry_keys=["hvac"])
    entry = (
        await api.post("/suppression", json={"kind": "company", "value": str(company.id)})
    ).json()
    buy_box = await hvac_buy_box(db_session)

    await api.delete(f"/suppression/{entry['id']}")
    outcome = await SearchService(db_session).run(buy_box)

    assert company.display_name in {item.name for item in outcome.scored}
    assert outcome.withheld == 0


class CapturingWriter:
    """Stands in for Claude and keeps the brief it was given."""

    def __init__(self) -> None:
        self.facts = ""

    async def write(self, *, company: str, facts: str, sender: str, purpose: str) -> OutreachDraft:
        self.facts = facts
        return OutreachDraft(subject="s", body="b", opening_fact="o", follow_up="f")


async def test_the_brief_holds_public_facts_with_true_sources_and_nothing_private(
    db_session: AsyncSession,
) -> None:
    """The founding year came from the website, so it must not be credited to a
    register; and a first message has no business knowing the owner's age."""
    company = await make_company(
        db_session,
        display_name="A/C Service Co.",
        summary="A family owned HVAC company in Fort Worth.",
        founded_year=1999,
        revenue_low=750_000,
        revenue_high=1_250_000,
    )
    await add_field(db_session, company, "founded_year", 1999, source=SourceName.WEBSITE)
    await add_field(
        db_session,
        company,
        "has_recurring_revenue",
        True,
        source=SourceName.WEBSITE,
        evidence="We offer commercial and residential preventative maintenance agreements.",
    )
    await add_person(db_session, company, "Pat Owner", role="Owner", is_owner=True, birth_year=1955)
    writer = CapturingWriter()

    await OutreachService(db_session, lambda: writer).draft(  # type: ignore[arg-type, return-value]
        company.id, SenderProfile(name="Bilal", background="Buying one HVAC business.")
    )

    assert "Founded in 1999, according to their website" in writer.facts
    assert "maintenance agreements" in writer.facts
    assert "Pat Owner, Owner" in writer.facts
    assert "1955" not in writer.facts and "born" not in writer.facts
    assert "revenue" not in writer.facts.lower()


async def test_a_blocked_website_is_matched_however_it_was_typed(
    api: AsyncClient, db_session: AsyncSession
) -> None:
    """Stored as typed, "https://www.Example.com/contact" never matched example.com."""
    company = await make_company(db_session, display_name="Typed Co", domain="typedco.com")

    response = await api.post(
        "/suppression", json={"kind": "domain", "value": "https://www.TypedCo.com/contact"}
    )

    assert response.status_code == 201
    assert response.json()["value"] == "typedco.com"
    assert company.id in await SuppressionRepository(db_session).blocked([company])


async def test_a_company_entry_that_is_not_an_id_is_a_clear_422(api: AsyncClient) -> None:
    response = await api.post("/suppression", json={"kind": "company", "value": "not-an-id"})

    assert response.status_code == 422
    assert "not a company id" in response.json()["error"]["message"]
