"""Stored revenue estimates: only for a known headcount, always with the arithmetic."""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from dealsignal.models.enums import SourceName
from dealsignal.repositories.company import CompanyRepository
from dealsignal.repositories.field_value import FieldValueRepository
from dealsignal.services.estimates import FIELD, record_revenue_estimate
from tests.integration.factories import NOW, make_company

pytestmark = pytest.mark.integration


async def test_an_estimate_from_a_register_band_is_stored_with_its_basis(
    db_session: AsyncSession,
) -> None:
    banded = await make_company(
        db_session, display_name="Band Co", employee_band="1-9", industry_keys=["hvac"]
    )
    await make_company(db_session, display_name="Unknown Size Co")
    fields = FieldValueRepository(db_session)

    estimable = await CompanyRepository(db_session).with_known_headcount()
    for company in estimable:
        await record_revenue_estimate(company, fields, observed_at=NOW)

    assert [company.display_name for company in estimable] == ["Band Co"]
    assert (banded.revenue_low, banded.revenue_high) == (5 * 150_000, 5 * 250_000)
    [stored] = await fields.for_company(banded.id, FIELD)
    assert stored.source == SourceName.ESTIMATE
    assert stored.evidence is not None
    assert "midpoint of the register's 1-9 band" in stored.evidence
