"""Do-not-contact storage."""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import or_, select
from sqlalchemy.dialects.postgresql import insert

from dealsignal.models.company import Company
from dealsignal.models.enums import SuppressionKind
from dealsignal.models.suppression import SuppressionEntry
from dealsignal.repositories.base import BaseRepository


class SuppressionRepository(BaseRepository[SuppressionEntry]):
    model = SuppressionEntry

    async def entries(self, *, limit: int = 200) -> list[SuppressionEntry]:
        result = await self.session.scalars(
            select(SuppressionEntry).order_by(SuppressionEntry.created_at.desc()).limit(limit)
        )
        return list(result)

    async def matching(self, company: Company) -> SuppressionEntry | None:
        """The entry that blocks this company, by its id or its domain."""
        conditions = [
            (SuppressionEntry.kind == SuppressionKind.COMPANY)
            & (SuppressionEntry.value == str(company.id))
        ]
        if company.domain:
            conditions.append(
                (SuppressionEntry.kind == SuppressionKind.DOMAIN)
                & (SuppressionEntry.value == company.domain.lower())
            )
        entry: SuppressionEntry | None = await self.session.scalar(
            select(SuppressionEntry).where(or_(*conditions)).limit(1)
        )
        return entry

    async def find(self, kind: SuppressionKind, value: str) -> SuppressionEntry | None:
        entry: SuppressionEntry | None = await self.session.scalar(
            select(SuppressionEntry).where(
                SuppressionEntry.kind == kind, SuppressionEntry.value == value
            )
        )
        return entry

    async def blocked(self, companies: Sequence[Company]) -> set[uuid.UUID]:
        """Which of these companies are blocked, by id or by domain, in one query."""
        if not companies:
            return set()

        ids = {str(company.id) for company in companies}
        domains = {company.domain.lower() for company in companies if company.domain}
        rows = await self.session.execute(
            select(SuppressionEntry.kind, SuppressionEntry.value).where(
                or_(
                    (SuppressionEntry.kind == SuppressionKind.COMPANY)
                    & SuppressionEntry.value.in_(ids),
                    (SuppressionEntry.kind == SuppressionKind.DOMAIN)
                    & SuppressionEntry.value.in_(domains or {""}),
                )
            )
        )
        blocked_ids: set[str] = set()
        blocked_domains: set[str] = set()
        for kind, value in rows:
            (blocked_ids if kind == SuppressionKind.COMPANY else blocked_domains).add(value)

        return {
            company.id
            for company in companies
            if str(company.id) in blocked_ids
            or (company.domain and company.domain.lower() in blocked_domains)
        }

    async def block(
        self,
        *,
        kind: SuppressionKind,
        value: str,
        reason: str | None,
        company_id: uuid.UUID | None = None,
    ) -> None:
        """Add an entry. Blocking the same thing twice is not an error.

        Named `block` rather than `add` so it does not clash with the base
        repository's `add`, which takes an entity.
        """
        statement = insert(SuppressionEntry).values(
            kind=kind, value=value, reason=reason, company_id=company_id
        )
        await self.session.execute(
            statement.on_conflict_do_nothing(constraint="uq_suppression_entry")
        )
