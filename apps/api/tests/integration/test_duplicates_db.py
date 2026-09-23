"""The review queue against a real database.

Persistence is checked with raw SQL rather than through the ORM, whose view of an
object can differ from what was committed.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from dealsignal.models.enums import SourceName
from tests.integration.factories import add_field, add_person, make_company, make_pair

pytestmark = pytest.mark.integration


async def scalar(session: AsyncSession, sql: str, **params: object) -> object:
    return (await session.execute(text(sql), params)).scalar()


async def test_merging_through_the_api_records_the_decision(
    api: AsyncClient, db_session: AsyncSession
) -> None:
    """The decision is committed before the response reports it."""
    keep = await make_company(db_session, display_name="Tri-Cities Air")
    absorb = await make_company(db_session, display_name="Tri-Cities Air")
    pair = await make_pair(db_session, keep, absorb)

    response = await api.post(f"/duplicates/{pair.id}/merge")

    assert response.status_code == 200
    assert (
        await scalar(db_session, "select status from duplicate_candidates where id = :i", i=pair.id)
        == "merged"
    )
    assert (
        await scalar(
            db_session, "select company_b_id from duplicate_candidates where id = :i", i=pair.id
        )
        is None
    )
    assert (
        await scalar(db_session, "select count(*) from companies where id = :i", i=absorb.id) == 0
    )


async def test_merge_moves_everything_onto_the_survivor(
    api: AsyncClient, db_session: AsyncSession
) -> None:
    keep = await make_company(db_session, display_name="Baker Brothers")
    absorb = await make_company(db_session, display_name="Baker Brothers")
    await add_field(db_session, keep, "display_name", "Baker Brothers")
    await add_field(db_session, absorb, "display_name", "Baker Brothers")  # collides
    await add_field(db_session, absorb, "phone_e164", "+12145550000", SourceName.WEBSITE)
    await add_person(db_session, absorb, "Pat Baker", is_owner=True, birth_year=1958)
    pair = await make_pair(db_session, keep, absorb)

    response = await api.post(f"/duplicates/{pair.id}/merge")

    assert response.status_code == 200
    fields = "select count(*) from field_values where company_id = :i and field = :f"
    assert await scalar(db_session, fields, i=keep.id, f="display_name") == 1, (
        "the collision is dropped, not duplicated"
    )
    assert await scalar(db_session, fields, i=keep.id, f="phone_e164") == 1, (
        "the new fact moves across"
    )
    assert (
        await scalar(db_session, "select count(*) from people where company_id = :i", i=keep.id)
        == 1
    )


async def test_merge_takes_the_domain_from_the_absorbed_record(
    api: AsyncClient, db_session: AsyncSession
) -> None:
    """A survivor without a website takes the absorbed record's."""
    keep = await make_company(db_session, display_name="Fort Worth Plumber", domain=None)
    absorb = await make_company(
        db_session, display_name="Fort Worth Plumber", domain="fortworthplumbertx.com"
    )
    pair = await make_pair(db_session, keep, absorb)

    response = await api.post(f"/duplicates/{pair.id}/merge")

    assert response.status_code == 200
    assert (
        await scalar(db_session, "select domain from companies where id = :i", i=keep.id)
        == "fortworthplumbertx.com"
    )


async def test_other_pairs_follow_the_absorbed_company(
    api: AsyncClient, db_session: AsyncSession
) -> None:
    keep = await make_company(db_session, display_name="Amick Plumbing")
    absorb = await make_company(db_session, display_name="Amick Plumbing")
    other = await make_company(db_session, display_name="Amick Plumbing Co")
    decided = await make_pair(db_session, keep, absorb)
    waiting = await make_pair(db_session, other, absorb)

    await api.post(f"/duplicates/{decided.id}/merge")

    row = (
        await db_session.execute(
            text(
                "select company_a_id, company_b_id, status from duplicate_candidates where id = :i"
            ),
            {"i": waiting.id},
        )
    ).one()
    assert row.status == "pending"
    assert keep.id in (row.company_a_id, row.company_b_id), (
        "the waiting pair now concerns the survivor"
    )
    assert absorb.id not in (row.company_a_id, row.company_b_id)


async def test_merging_twice_is_refused_with_a_reason(
    api: AsyncClient, db_session: AsyncSession
) -> None:
    pair = await make_pair(
        db_session,
        await make_company(db_session, display_name="Woodie Woods"),
        await make_company(db_session, display_name="Woodie Woods"),
    )
    await api.post(f"/duplicates/{pair.id}/merge")

    response = await api.post(f"/duplicates/{pair.id}/merge")

    assert response.status_code == 409
    assert "already been merged" in response.json()["error"]["message"]


async def test_rejecting_keeps_both_companies(api: AsyncClient, db_session: AsyncSession) -> None:
    first = await make_company(db_session, display_name="Stark Services")
    second = await make_company(db_session, display_name="Stark Services Dallas")
    pair = await make_pair(db_session, first, second)

    response = await api.post(f"/duplicates/{pair.id}/reject")

    assert response.status_code == 200
    assert (
        await scalar(db_session, "select status from duplicate_candidates where id = :i", i=pair.id)
        == "rejected"
    )
    assert (
        await scalar(
            db_session,
            "select count(*) from companies where id in (:a, :b)",
            a=first.id,
            b=second.id,
        )
        == 2
    )


async def test_the_queue_lists_only_pairs_still_waiting(
    api: AsyncClient, db_session: AsyncSession
) -> None:
    waiting = await make_pair(
        db_session,
        await make_company(db_session, display_name="Casey Sheet Metal"),
        await make_company(db_session, display_name="Casey Sheet Metal"),
    )
    decided = await make_pair(
        db_session,
        await make_company(db_session, display_name="Bock Services"),
        await make_company(db_session, display_name="Bock Services"),
    )
    await api.post(f"/duplicates/{decided.id}/reject")

    listed = {pair["id"] for pair in (await api.get("/duplicates")).json()}

    assert str(waiting.id) in listed
    assert str(decided.id) not in listed


async def test_the_reviewer_can_keep_the_second_record(
    api: AsyncClient, db_session: AsyncSession
) -> None:
    """A dentist's listing merged into the practice must keep the practice's name,
    and the decision must survive the first record being deleted."""
    dentist = await make_company(db_session, display_name="Kristy Hong")
    practice = await make_company(db_session, display_name="Kreating Smiles Pediatric Dentistry")
    pair = await make_pair(db_session, dentist, practice)

    response = await api.post(f"/duplicates/{pair.id}/merge?keep=b")

    assert response.status_code == 200
    assert response.json()["message"] == "Merged into Kreating Smiles Pediatric Dentistry."
    assert (
        await scalar(db_session, "select count(*) from companies where id = :i", i=dentist.id) == 0
    )
    decision = (
        await db_session.execute(
            text("select status, company_a_id from duplicate_candidates where id = :i"),
            {"i": pair.id},
        )
    ).one()
    assert tuple(decision) == ("merged", practice.id)


async def test_a_pair_the_survivor_already_has_is_not_duplicated(
    api: AsyncClient, db_session: AsyncSession
) -> None:
    """Kristy Hong was paired with her practice and with a colleague, who was paired
    with the practice too. Merging her into the practice made a second colleague-and-
    practice pair, and the database refused the whole merge with a 500."""
    dentist = await make_company(db_session, display_name="Kristy Hong")
    practice = await make_company(db_session, display_name="Kreating Smiles Pediatric Dentistry")
    colleague = await make_company(db_session, display_name="Gene Kouri, DDS")
    pair = await make_pair(db_session, dentist, practice)
    await make_pair(db_session, colleague, dentist)
    await make_pair(db_session, colleague, practice)

    response = await api.post(f"/duplicates/{pair.id}/merge?keep=b")

    assert response.status_code == 200
    waiting = (
        await db_session.execute(
            text(
                "select company_a_id, company_b_id from duplicate_candidates "
                "where status = 'pending'"
            )
        )
    ).all()
    assert [set(row) for row in waiting] == [{colleague.id, practice.id}]
