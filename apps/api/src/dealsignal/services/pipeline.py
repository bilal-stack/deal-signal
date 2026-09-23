"""Working leads through the deal board."""

from __future__ import annotations

import uuid
from datetime import date

from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from dealsignal.core.errors import NotFoundError
from dealsignal.models.enums import PipelineStage
from dealsignal.models.pipeline import PipelineItem
from dealsignal.repositories.company import CompanyRepository
from dealsignal.repositories.pipeline import PipelineRepository

MAX_NOTES_CHARS = 5_000


class PipelineUpdate(BaseModel):
    """A partial change. Fields left unset are not touched."""

    model_config = ConfigDict(frozen=True)

    stage: PipelineStage | None = None
    notes: str | None = None
    next_action_on: date | None = None
    clear_next_action: bool = False


class PipelineService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._items = PipelineRepository(session)
        self._companies = CompanyRepository(session)

    async def add(self, company_id: uuid.UUID) -> tuple[PipelineItem, bool]:
        """Put a company on the board. Returns the item and whether it was new.

        Adding a company twice is not an error: the existing card is returned, so a
        double click never creates a second copy.
        """
        existing = await self._items.for_company(company_id)
        if existing is not None:
            return existing, False

        if await self._companies.get(company_id) is None:
            raise NotFoundError(f"No company with id {company_id}.")

        item = self._items.add(PipelineItem(company_id=company_id, stage=PipelineStage.NEW))
        await self._session.flush()
        return item, True

    async def update(self, item_id: uuid.UUID, change: PipelineUpdate) -> PipelineItem:
        item = await self._items.get_or_raise(item_id)
        if change.stage is not None:
            item.stage = change.stage
        if change.notes is not None:
            item.notes = change.notes[:MAX_NOTES_CHARS] or None
        if change.clear_next_action:
            item.next_action_on = None
        elif change.next_action_on is not None:
            item.next_action_on = change.next_action_on
        await self._session.flush()
        return item

    async def remove(self, item_id: uuid.UUID) -> None:
        item = await self._items.get_or_raise(item_id)
        await self._items.delete(item)
        await self._session.flush()
