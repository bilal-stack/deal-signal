"""Ingest against a real database: matching, provenance and the review queue."""

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from dealsignal.models.enums import Country, SourceName
from dealsignal.services.ingest import PlaceIngestService, SkippedRecord
from dealsignal.sources.base import PlaceRecord
from dealsignal.sources.industries import Industry, resolve

pytestmark = pytest.mark.integration


def place(external_id: str, **overrides: object) -> PlaceRecord:
    defaults: dict[str, object] = {
        "source": SourceName.OVERTURE,
        "external_id": external_id,
        "name": "Baker Brothers Plumbing & Air",
        "country": Country.US,
        "city": "Mesquite",
        "website": "https://bakerbrothersplumbing.com",
        "phone": "(214) 892-2350",
        "latitude": 32.79,
        "longitude": -96.63,
        "category": "hvac_services",
    }
    return PlaceRecord(**{**defaults, **overrides})


async def count(session: AsyncSession, sql: str) -> int:
    return int((await session.execute(text(sql))).scalar() or 0)


async def test_ingesting_the_same_records_twice_changes_nothing(db_session: AsyncSession) -> None:
    """Re-running a seed must never duplicate companies or pile up provenance rows."""
    industry = resolve("hvac")
    assert industry is not None
    records = [
        place("ov-1"),
        place(
            "ov-2",
            name="Craddock Lumber",
            website="https://craddocklumber.com",
            phone="(214) 555-0101",
        ),
    ]
    service = PlaceIngestService(db_session)

    first = await service.ingest(records, industry=industry)
    companies_after_first = await count(db_session, "select count(*) from companies")
    fields_after_first = await count(db_session, "select count(*) from field_values")

    second = await service.ingest(records, industry=industry)

    assert first.created == 2
    assert second.created == 0
    assert second.merged == 2
    assert await count(db_session, "select count(*) from companies") == companies_after_first
    assert await count(db_session, "select count(*) from field_values") == fields_after_first


async def test_provenance_is_recorded_for_every_known_field(db_session: AsyncSession) -> None:
    industry = resolve("hvac")
    assert industry is not None

    await PlaceIngestService(db_session).ingest([place("ov-1", street=None)], industry=industry)

    recorded = {
        row[0] for row in await db_session.execute(text("select distinct field from field_values"))
    }
    assert {"display_name", "domain", "phone_e164", "city", "category"} <= recorded
    assert "street" not in recorded, "an unknown value is not recorded as a fact"


async def test_an_uncertain_match_is_queued_rather_than_guessed(db_session: AsyncSession) -> None:
    """Same phone, similar name, but two kilometres apart and no shared website: worth
    a human look, not a merge. At one address, the same pair would merge."""
    industry = resolve("hvac")
    assert industry is not None
    service = PlaceIngestService(db_session)

    await service.ingest(
        [place("ov-1", name="Tri-Cities Air", website=None, phone="(817) 246-2488")],
        industry=industry,
    )
    report = await service.ingest(
        [
            place(
                "ov-2",
                name="Tri Cities Air Conditioning",
                website=None,
                phone="(817) 246-2488",
                latitude=32.808,
            )
        ],
        industry=industry,
    )

    assert report.needs_review == 1
    assert await count(db_session, "select count(*) from companies") == 2, "not merged on a guess"
    assert (
        await count(
            db_session, "select count(*) from duplicate_candidates where status = 'pending'"
        )
        == 1
    )


async def test_a_shared_website_merges_without_asking(db_session: AsyncSession) -> None:
    industry = resolve("hvac")
    assert industry is not None
    service = PlaceIngestService(db_session)

    await service.ingest([place("ov-1")], industry=industry)
    report = await service.ingest(
        [place("ov-2", name="Baker Bros Plumbing and Air Conditioning", phone=None)],
        industry=industry,
    )

    assert report.merged == 1
    assert report.needs_review == 0
    assert await count(db_session, "select count(*) from companies") == 1


async def test_a_plumbing_search_does_not_leak_into_hvac_results(db_session: AsyncSession) -> None:
    """HVAC and plumbing share one official industry code. Filtering by that code put
    every plumber into HVAC searches, the same relevance failure as the tool we replace."""
    from dealsignal.models.buy_box import BuyBox
    from dealsignal.services.search import SearchService

    hvac, plumbing = resolve("hvac"), resolve("plumbing")
    assert hvac is not None and plumbing is not None
    service = PlaceIngestService(db_session)
    await service.ingest(
        [
            place(
                "ov-h",
                name="Aire Serv of Fort Worth",
                website="https://aireserv.com",
                phone="(817) 555-0100",
            )
        ],
        industry=hvac,
    )
    await service.ingest(
        [
            place(
                "ov-p",
                name="Amick Plumbing",
                website="https://amickplumbing.com",
                phone="(817) 555-0199",
            )
        ],
        industry=plumbing,
    )
    buy_box = BuyBox(name="HVAC only", industries=["hvac"], countries=["US"], weights={})
    db_session.add(buy_box)
    await db_session.flush()

    names = {item.name for item in (await SearchService(db_session).run(buy_box)).scored}

    assert "Aire Serv of Fort Worth" in names
    assert "Amick Plumbing" not in names


async def test_a_company_found_by_two_searches_belongs_to_both(db_session: AsyncSession) -> None:
    hvac, plumbing = resolve("hvac"), resolve("plumbing")
    assert hvac is not None and plumbing is not None
    service = PlaceIngestService(db_session)

    await service.ingest([place("ov-1", name="Berkeys Plumbing, A/C & Electrical")], industry=hvac)
    await service.ingest(
        [place("ov-2", name="Berkeys Plumbing, A/C & Electrical")], industry=plumbing
    )

    keys = await db_session.scalar(text("select industry_keys from companies"))
    assert sorted(keys) == ["hvac", "plumbing"]


async def test_a_shared_domain_is_found_even_in_a_crowded_neighbourhood(
    db_session: AsyncSession,
) -> None:
    """A company sharing this website is found even where many similar names are
    nearby and the candidate list is capped."""
    plumbing = resolve("plumbing")
    assert plumbing is not None
    service = PlaceIngestService(db_session)

    crowd = [
        place(
            f"crowd-{index}",
            name=f"Houston Plumbing Co {index}",
            website=f"https://houstonplumbing{index}.com",
            phone=f"(713) 555-{index:04d}",
            latitude=29.76 + index * 0.00001,
            longitude=-95.37,
        )
        for index in range(30)
    ]
    await service.ingest(crowd, industry=plumbing)

    original = place(
        "chain-1",
        name="Houston Plumbing Pros",
        website="https://houstonplumbingpros.com",
        phone="(713) 555-9999",
        latitude=29.76,
        longitude=-95.37,
    )
    await service.ingest([original], industry=plumbing)

    branch = place(
        "chain-2",
        name="Houston Plumbing Pros LLC",
        website="https://houstonplumbingpros.com/",
        phone="(713) 555-8888",
        latitude=29.76,
        longitude=-95.37,
    )
    report = await service.ingest([branch], industry=plumbing)

    assert report.skipped == 0
    assert report.merged == 1, "the shared domain decides it, however crowded the area"


async def test_one_refused_record_does_not_lose_the_batch(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Whatever the cause, a refused record is skipped and reported; the rest are kept."""
    hvac = resolve("hvac")
    assert hvac is not None
    service = PlaceIngestService(db_session)
    store = service._ingest_one

    async def refuse_one(record: PlaceRecord, industry: Industry) -> tuple[bool, int]:
        if record.external_id == "refused":
            conflict = Exception("Key (domain)=(refused.com) already exists.")
            raise IntegrityError("INSERT INTO companies", {}, conflict)
        return await store(record, industry)

    monkeypatch.setattr(service, "_ingest_one", refuse_one)
    records = [
        place("kept-1", name="First Kept Co", website="https://firstkept.com", phone=None),
        place("refused", name="Refused Co", website="https://refused.com", phone=None),
        place("kept-2", name="Second Kept Co", website="https://secondkept.com", phone=None),
    ]

    report = await service.ingest(records, industry=hvac)

    assert (report.seen, report.created, report.skipped) == (3, 2, 1)
    assert report.skips == [
        SkippedRecord(name="Refused Co", reason="the database refused this record")
    ]
    assert await count(db_session, "select count(*) from companies") == 2


async def test_two_businesses_on_one_site_builder_stay_apart(db_session: AsyncSession) -> None:
    """Two businesses whose pages sit on one site builder are not the same business."""
    hvac = resolve("hvac")
    assert hvac is not None
    records = [
        place(
            "sb-1",
            name="Northside Air Conditioning",
            website="https://northside-air.business.site",
            phone="(832) 555-0101",
        ),
        place(
            "sb-2",
            name="Elm Street Plumbing",
            website="https://elm-street-plumbing.business.site",
            phone="(832) 555-0102",
        ),
    ]

    report = await PlaceIngestService(db_session).ingest(records, industry=hvac)

    assert (report.created, report.merged, report.needs_review) == (2, 0, 0)
    assert await count(db_session, "select count(*) from companies where domain is not null") == 0


async def test_franchise_locations_are_both_kept_and_sent_to_review(
    db_session: AsyncSession,
) -> None:
    """One brand website, two separately owned locations: both are kept, and the pair
    goes to review rather than being merged or dropped."""
    hvac = resolve("hvac")
    assert hvac is not None
    records = [
        place(
            "fr-1",
            name="Comfort Pros of Fort Worth",
            website="https://comfortpros.com/fort-worth/",
            phone="(817) 555-0170",
            latitude=32.75,
            longitude=-97.33,
        ),
        place(
            "fr-2",
            name="Comfort Pros of Sugar Land",
            website="https://comfortpros.com/sugar-land/",
            phone="(281) 555-0171",
            latitude=29.62,
            longitude=-95.63,
        ),
    ]
    service = PlaceIngestService(db_session)

    first = await service.ingest(records[:1], industry=hvac)
    second = await service.ingest(records[1:], industry=hvac)

    assert (first.created, second.created, second.skipped) == (1, 1, 0)
    assert second.needs_review == 1
    reason = await db_session.scalar(text("select reason from duplicate_candidates"))
    assert reason == "Same website, but different location pages: a chain or a franchise?"
