"""Register enrichment and scoring against a real database."""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from dealsignal.models.buy_box import BuyBox, Score
from dealsignal.models.enums import Country, SourceName
from dealsignal.services.registry_enrichment import RegistryEnrichmentService
from dealsignal.services.scoring_service import ScoringService
from dealsignal.services.search import SearchService
from dealsignal.sources.base import OfficerRecord, RegistryRecord, RegistrySource
from tests.integration.factories import add_person, make_company

pytestmark = pytest.mark.integration

PEOPLE_FOR_COMPANY = """
    select full_name, is_company, birth_year
    from people
    where company_id = :i
    order by full_name
"""


class FakeFrenchRegister(RegistrySource):
    """A register that answers with a fixed record, or with nothing."""

    name = SourceName.RECHERCHE_ENTREPRISES
    countries = frozenset({Country.FR})

    def __init__(self, record: RegistryRecord | None) -> None:
        self._record = record

    async def is_available(self) -> bool:
        return True

    async def lookup(
        self, *, name: str, country: Country, city: str | None = None
    ) -> RegistryRecord | None:
        return self._record


def french_record() -> RegistryRecord:
    return RegistryRecord(
        source=SourceName.RECHERCHE_ENTREPRISES,
        registry_id="438085045",
        legal_name="MOUNIER SANITAIRE",
        country=Country.FR,
        incorporated_on=date(1986, 3, 1),
        industry_code="238220",
        status="A",
        employee_band="10-19",
        officers=(
            OfficerRecord(full_name="Joseph Sebban", role="Gérant", birth_year=1942, is_owner=True),
            OfficerRecord(full_name="MAPA", role="Président", is_owner=True, is_company=True),
        ),
    )


async def test_register_data_lands_with_a_real_owner_and_a_parent_signal(
    db_session: AsyncSession,
) -> None:
    company = await make_company(
        db_session, display_name="Mounier Sanitaire", country=Country.FR, industry_code="238220"
    )
    service = RegistryEnrichmentService(db_session, [FakeFrenchRegister(french_record())])

    outcome = await service.enrich(company)
    await db_session.flush()  # raw SQL below does not trigger SQLAlchemy's autoflush

    assert outcome.succeeded
    rows = (
        await db_session.execute(
            text(PEOPLE_FOR_COMPANY),
            {"i": company.id},
        )
    ).all()
    assert [(row.full_name, row.is_company, row.birth_year) for row in rows] == [
        ("Joseph Sebban", False, 1942),
        ("MAPA", True, None),
    ]
    assert company.founded_year == 1986
    assert company.revenue_low is not None, "the headcount band feeds a revenue estimate"
    parent = await db_session.scalar(
        text("select value from field_values where company_id = :i and field = 'is_part_of_group'"),
        {"i": company.id},
    )
    assert parent is True


async def test_rerunning_the_register_does_not_duplicate_people(db_session: AsyncSession) -> None:
    company = await make_company(db_session, display_name="Mounier Sanitaire", country=Country.FR)
    service = RegistryEnrichmentService(db_session, [FakeFrenchRegister(french_record())])

    await service.enrich(company)
    await service.enrich(company)
    await db_session.flush()

    people = await db_session.scalar(
        text("select count(*) from people where company_id = :i"), {"i": company.id}
    )
    assert people == 2


async def test_no_match_stores_nothing_and_says_so(db_session: AsyncSession) -> None:
    company = await make_company(db_session, display_name="Atout Energie", country=Country.FR)
    service = RegistryEnrichmentService(db_session, [FakeFrenchRegister(None)])

    outcome = await service.enrich(company)

    assert outcome.succeeded is False
    assert "No match" in outcome.message
    assert company.legal_name is None


async def test_a_country_without_a_register_is_explained(db_session: AsyncSession) -> None:
    company = await make_company(db_session, display_name="Stark Services", country=Country.US)
    service = RegistryEnrichmentService(db_session, [FakeFrenchRegister(french_record())])

    outcome = await service.enrich(company)

    assert outcome.succeeded is False
    assert "No free public register covers US" in outcome.message


async def test_an_unscorable_company_is_stored_with_no_score(db_session: AsyncSession) -> None:
    """Unknown must be NULL in the database, never a zero that reads as "bad"."""
    company = await make_company(db_session, display_name="Know Nothing Ltd")
    buy_box = BuyBox(name="Anything", industries=["hvac"], countries=["US"], weights={})
    db_session.add(buy_box)
    await db_session.flush()

    await ScoringService(db_session).score_company(company, buy_box)

    stored = await db_session.scalar(
        text("select score from scores where company_id = :i"), {"i": company.id}
    )
    assert stored is None


async def test_rescoring_replaces_the_previous_score(db_session: AsyncSession) -> None:
    company = await make_company(db_session, display_name="Old Firm", founded_year=1980)
    buy_box = BuyBox(name="Established", industries=["hvac"], countries=["US"], weights={})
    db_session.add(buy_box)
    await db_session.flush()
    service = ScoringService(db_session)

    await service.score_company(company, buy_box)
    company.founded_year = 2024
    await service.score_company(company, buy_box)

    rows = list(
        await db_session.scalars(
            select(Score).where(Score.company_id == company.id, Score.buy_box_id == buy_box.id)
        )
    )
    assert len(rows) == 1, "one score per company per Buy Box"
    assert rows[0].score is not None
    assert rows[0].score < 50, "the newer, younger founding year replaced the old score"


async def test_the_buy_box_mode_chooses_the_signal_set(db_session: AsyncSession) -> None:
    """A named contact matters to a salesperson and says nothing about a sale of the
    business, so the same company scores under one mode and not the other."""
    company = await make_company(db_session, display_name="Contactable Ltd")
    await add_person(db_session, company, "Joseph Sebban", is_owner=True)
    service = ScoringService(db_session)

    sales_box = BuyBox(
        name="Sell to", mode="sales", industries=["hvac"], countries=["US"], weights={}
    )
    acquisition_box = BuyBox(
        name="Buy", mode="acquisition", industries=["hvac"], countries=["US"], weights={}
    )
    db_session.add_all([sales_box, acquisition_box])
    await db_session.flush()

    as_prospect = await service.score_company(company, sales_box)
    as_target = await service.score_company(company, acquisition_box)

    assert as_prospect.result.score == 100
    assert "decision-maker" in as_prospect.result.reasons[0].reason
    assert as_target.result.score is None, "no acquisition signal reads a contact's existence"


async def test_search_results_carry_a_position_only_when_one_is_known(
    db_session: AsyncSession,
) -> None:
    """A company with no location must not be dropped on the map at 0,0."""
    placed = await make_company(
        db_session,
        display_name="Placed HVAC",
        industry_keys=["hvac"],
        geo="SRID=4326;POINT(-96.63 32.79)",
    )
    unplaced = await make_company(db_session, display_name="Unplaced HVAC", industry_keys=["hvac"])
    buy_box = BuyBox(name="Map", industries=["hvac"], countries=["US"], weights={})
    db_session.add(buy_box)
    await db_session.flush()

    outcome = await SearchService(db_session).run(buy_box)
    by_name = {item.name: item for item in outcome.scored}

    assert by_name[placed.display_name].latitude == pytest.approx(32.79)
    assert by_name[placed.display_name].longitude == pytest.approx(-96.63)
    assert by_name[unplaced.display_name].latitude is None
    assert by_name[unplaced.display_name].longitude is None
