"""The deal board against a real database, through the API."""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from tests.integration.factories import make_company

pytestmark = pytest.mark.integration


async def test_adding_a_company_puts_it_in_the_first_stage(
    api: AsyncClient, db_session: AsyncSession
) -> None:
    company = await make_company(db_session, display_name="Mounier Sanitaire")

    response = await api.post("/pipeline", json={"company_id": str(company.id)})

    assert response.status_code == 201
    assert response.json()["stage"] == "new"


async def test_adding_the_same_company_twice_returns_the_existing_card(
    api: AsyncClient, db_session: AsyncSession
) -> None:
    """A double click must never create a second card."""
    company = await make_company(db_session, display_name="Arma Plomberie")

    first = await api.post("/pipeline", json={"company_id": str(company.id)})
    second = await api.post("/pipeline", json={"company_id": str(company.id)})

    assert second.status_code == 200
    assert second.json()["id"] == first.json()["id"]
    count = await db_session.scalar(
        text("select count(*) from pipeline_items where company_id = :i"), {"i": company.id}
    )
    assert count == 1


async def test_moving_a_card_and_adding_notes_persists(
    api: AsyncClient, db_session: AsyncSession
) -> None:
    company = await make_company(db_session, display_name="Cassard et Bazin")
    card = (await api.post("/pipeline", json={"company_id": str(company.id)})).json()

    response = await api.patch(
        f"/pipeline/{card['id']}",
        json={
            "stage": "contacted",
            "notes": "Left a message with the office.",
            "next_action_on": "2026-09-24",
        },
    )

    assert response.status_code == 200
    row = (
        await db_session.execute(
            text("select stage, notes, next_action_on from pipeline_items where id = :i"),
            {"i": card["id"]},
        )
    ).one()
    assert row.stage == "contacted"
    assert row.notes == "Left a message with the office."
    assert str(row.next_action_on) == "2026-09-24"


async def test_a_follow_up_date_can_be_cleared(api: AsyncClient, db_session: AsyncSession) -> None:
    company = await make_company(db_session, display_name="Abritherm")
    card = (await api.post("/pipeline", json={"company_id": str(company.id)})).json()
    await api.patch(f"/pipeline/{card['id']}", json={"next_action_on": "2026-10-01"})

    response = await api.patch(f"/pipeline/{card['id']}", json={"clear_next_action": True})

    assert response.json()["next_action_on"] is None


async def test_an_unknown_stage_is_refused(api: AsyncClient, db_session: AsyncSession) -> None:
    company = await make_company(db_session, display_name="Brunel Plomberie")
    card = (await api.post("/pipeline", json={"company_id": str(company.id)})).json()

    response = await api.patch(f"/pipeline/{card['id']}", json={"stage": "maybe-later"})

    assert response.status_code == 422


async def test_adding_a_company_that_does_not_exist_is_a_404(api: AsyncClient) -> None:
    response = await api.post(
        "/pipeline", json={"company_id": "00000000-0000-0000-0000-000000000000"}
    )

    assert response.status_code == 404


async def test_the_board_lists_stages_in_order(api: AsyncClient, db_session: AsyncSession) -> None:
    company = await make_company(db_session, display_name="Chouquet Services")
    await api.post("/pipeline", json={"company_id": str(company.id)})

    board = (await api.get("/pipeline")).json()

    assert board["stages"] == ["new", "contacted", "replied", "meeting", "offer", "won", "lost"]
    assert any(card["name"] == "Chouquet Services" for card in board["cards"])


async def test_removing_a_card_keeps_the_company(
    api: AsyncClient, db_session: AsyncSession
) -> None:
    company = await make_company(db_session, display_name="Bodevigie")
    card = (await api.post("/pipeline", json={"company_id": str(company.id)})).json()

    response = await api.delete(f"/pipeline/{card['id']}")

    assert response.status_code == 204
    assert (
        await db_session.scalar(
            text("select count(*) from companies where id = :i"), {"i": company.id}
        )
        == 1
    )
