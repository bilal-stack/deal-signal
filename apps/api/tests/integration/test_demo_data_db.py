"""The committed demo dataset must load back exactly what was exported."""

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from dealsignal.models.buy_box import BuyBox
from dealsignal.models.enums import SourceName
from dealsignal.scripts.demo_data import DemoDataError, restore, snapshot
from tests.integration.factories import add_field, add_person, make_company

pytestmark = pytest.mark.integration


async def test_a_snapshot_restores_every_fact_where_it_was(db_session: AsyncSession) -> None:
    company = await make_company(
        db_session,
        display_name="A/C Service Co.",
        domain="checkmyac.com",
        industry_keys=["hvac", "plumbing"],
        geo="SRID=4326;POINT(-97.3313 32.7261)",
    )
    await add_field(
        db_session,
        company,
        "has_recurring_revenue",
        True,
        source=SourceName.WEBSITE,
        evidence="We offer commercial and residential preventative maintenance agreements.",
    )
    await add_person(db_session, company, "Marie Durand", is_owner=True, birth_year=1961)
    db_session.add(
        BuyBox(name="Demo box", industries=["hvac"], countries=["US"], weights={"owner_age": 20})
    )
    await db_session.flush()

    dataset = await snapshot(db_session, buy_box_names=["Demo box"])
    await restore(db_session, dataset, replace=True)

    restored = (
        await db_session.execute(
            text(
                "select display_name, domain, industry_keys, st_astext(geo::geometry) "
                "from companies where id = :id"
            ),
            {"id": company.id},
        )
    ).one()
    assert tuple(restored) == (
        "A/C Service Co.",
        "checkmyac.com",
        ["hvac", "plumbing"],
        "POINT(-97.3313 32.7261)",
    )
    evidence = await db_session.scalar(
        text("select evidence from field_values where company_id = :id"), {"id": company.id}
    )
    assert evidence == "We offer commercial and residential preventative maintenance agreements."
    assert await db_session.scalar(text("select birth_year from people")) == 1961
    assert await db_session.scalar(text("select weights from buy_boxes")) == {"owner_age": 20}


async def test_existing_data_is_never_overwritten_without_asking(db_session: AsyncSession) -> None:
    await make_company(db_session, display_name="Someone's Real Data")
    dataset = await snapshot(db_session, buy_box_names=[])

    with pytest.raises(DemoDataError, match="--replace"):
        await restore(db_session, dataset, replace=False)


async def test_a_dataset_from_another_schema_is_refused(db_session: AsyncSession) -> None:
    dataset = await snapshot(db_session, buy_box_names=[])
    dataset["alembic_revision"] = "an-older-schema"

    with pytest.raises(DemoDataError, match="migrates"):
        await restore(db_session, dataset, replace=True)
