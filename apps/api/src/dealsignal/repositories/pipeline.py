"""Pipeline storage."""

from __future__ import annotations

import uuid

from sqlalchemy import select

from dealsignal.models.company import Company
from dealsignal.models.pipeline import PipelineItem
from dealsignal.repositories.base import BaseRepository


class PipelineRepository(BaseRepository[PipelineItem]):
    model = PipelineItem

    async def for_company(self, company_id: uuid.UUID) -> PipelineItem | None:
        item: PipelineItem | None = await self.session.scalar(
            select(PipelineItem).where(PipelineItem.company_id == company_id)
        )
        return item

    async def board(self) -> list[tuple[PipelineItem, Company]]:
        """Every item with its company, soonest follow-up first within a stage."""
        rows = await self.session.execute(
            select(PipelineItem, Company)
            .join(Company, Company.id == PipelineItem.company_id)
            .order_by(PipelineItem.next_action_on.asc().nulls_last(), Company.display_name)
        )
        return [(item, company) for item, company in rows.tuples()]
