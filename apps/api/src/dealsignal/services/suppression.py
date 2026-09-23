"""The do-not-contact list: what can be blocked, and in what form it is kept.

Entries are normalised on the way in, so a block always matches what searches,
exports and drafts compare against: a company by its id, a website by its domain.
"""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from dealsignal.core.errors import NotFoundError, ValidationError
from dealsignal.matching.normalize import normalize_domain
from dealsignal.models.enums import SuppressionKind
from dealsignal.models.suppression import SuppressionEntry
from dealsignal.repositories.company import CompanyRepository
from dealsignal.repositories.suppression import SuppressionRepository


class SuppressionService:
    def __init__(self, session: AsyncSession) -> None:
        self._entries = SuppressionRepository(session)
        self._companies = CompanyRepository(session)

    async def entries(self) -> list[SuppressionEntry]:
        return await self._entries.entries()

    async def block(
        self, kind: SuppressionKind, value: str, reason: str | None
    ) -> SuppressionEntry:
        """Add an entry, or return the existing one: blocking twice is not an error."""
        key, company_id = await self._normalise(kind, value)
        await self._entries.block(kind=kind, value=key, reason=reason, company_id=company_id)
        entry = await self._entries.find(kind, key)
        if entry is None:
            raise NotFoundError("The entry could not be read back after saving.")
        return entry

    async def unblock(self, entry_id: uuid.UUID) -> None:
        await self._entries.delete(await self._entries.get_or_raise(entry_id))

    async def _normalise(self, kind: SuppressionKind, value: str) -> tuple[str, uuid.UUID | None]:
        if kind is SuppressionKind.COMPANY:
            try:
                company_id = uuid.UUID(value.strip())
            except ValueError as exc:
                raise ValidationError(f"{value!r} is not a company id.") from exc
            if await self._companies.get(company_id) is None:
                raise NotFoundError(f"No company with id {company_id}.")
            return str(company_id), company_id

        domain = normalize_domain(value)
        if domain is None:
            raise ValidationError(f"{value!r} is not a website or domain.")
        return domain, None
