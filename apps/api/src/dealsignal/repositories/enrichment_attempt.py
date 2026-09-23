"""Remembering what each enrichment job tried, so the next run moves on."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from dealsignal.models.enrichment import EnrichmentAttempt
from dealsignal.models.enums import EnrichmentTask
from dealsignal.repositories.base import BaseRepository


class EnrichmentAttemptRepository(BaseRepository[EnrichmentAttempt]):
    model = EnrichmentAttempt

    async def record(
        self, company_id: uuid.UUID, task: EnrichmentTask, *, succeeded: bool, message: str
    ) -> None:
        """Keep the latest attempt only: the history adds nothing a user acts on."""
        statement = insert(EnrichmentAttempt).values(
            company_id=company_id,
            task=task,
            attempted_at=datetime.now(UTC),
            succeeded=succeeded,
            message=message,
        )
        await self.session.execute(
            statement.on_conflict_do_update(
                index_elements=[EnrichmentAttempt.company_id, EnrichmentAttempt.task],
                set_={
                    "attempted_at": statement.excluded.attempted_at,
                    "succeeded": statement.excluded.succeeded,
                    "message": statement.excluded.message,
                },
            )
        )

    async def for_company(self, company_id: uuid.UUID) -> list[EnrichmentAttempt]:
        result = await self.session.scalars(
            select(EnrichmentAttempt)
            .where(EnrichmentAttempt.company_id == company_id)
            .order_by(EnrichmentAttempt.attempted_at.desc())
        )
        return list(result)
