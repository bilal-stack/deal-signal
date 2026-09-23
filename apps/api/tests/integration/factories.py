"""Small builders for test data, so each test states only what it cares about."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from dealsignal.models.company import Company
from dealsignal.models.duplicate import DuplicateCandidate
from dealsignal.models.enums import Country, DuplicateStatus, SourceName
from dealsignal.models.person import Person
from dealsignal.models.source import FieldValue

NOW = datetime(2026, 9, 17, tzinfo=UTC)


async def make_company(session: AsyncSession, **overrides: Any) -> Company:
    name = overrides.pop("display_name", f"Company {uuid.uuid4().hex[:6]}")
    company = Company(
        display_name=name,
        normalized_name=name.lower(),
        country=overrides.pop("country", Country.US),
        **overrides,
    )
    session.add(company)
    await session.flush()
    return company


async def add_field(
    session: AsyncSession,
    company: Company,
    field: str,
    value: Any,
    source: SourceName = SourceName.OVERTURE,
    evidence: str | None = None,
) -> FieldValue:
    row = FieldValue(
        company_id=company.id,
        field=field,
        value=value,
        source=source,
        confidence=0.7,
        observed_at=NOW,
        evidence=evidence,
    )
    session.add(row)
    await session.flush()
    return row


async def add_person(
    session: AsyncSession, company: Company, name: str, **overrides: Any
) -> Person:
    person = Person(
        company_id=company.id,
        full_name=name,
        source=overrides.pop("source", SourceName.RECHERCHE_ENTREPRISES),
        **overrides,
    )
    session.add(person)
    await session.flush()
    return person


async def make_pair(
    session: AsyncSession, first: Company, second: Company, similarity: float = 0.85
) -> DuplicateCandidate:
    pair = DuplicateCandidate(
        company_a_id=first.id,
        company_b_id=second.id,
        similarity=similarity,
        reason="Same phone number, near-identical name",
        status=DuplicateStatus.PENDING,
    )
    session.add(pair)
    await session.flush()
    return pair
