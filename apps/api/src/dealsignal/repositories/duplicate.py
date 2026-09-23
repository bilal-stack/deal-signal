"""Storage for the duplicate review queue."""

from __future__ import annotations

import uuid

from sqlalchemy import case, delete, exists, or_, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import aliased

from dealsignal.models.duplicate import DuplicateCandidate
from dealsignal.models.enums import DuplicateStatus
from dealsignal.repositories.base import BaseRepository


class DuplicateRepository(BaseRepository[DuplicateCandidate]):
    model = DuplicateCandidate

    async def pending(self, *, limit: int = 50) -> list[DuplicateCandidate]:
        """Pairs still waiting on a decision, most similar first."""
        result = await self.session.scalars(
            select(DuplicateCandidate)
            .where(
                DuplicateCandidate.status == DuplicateStatus.PENDING,
                DuplicateCandidate.company_b_id.is_not(None),
            )
            .order_by(DuplicateCandidate.similarity.desc())
            .limit(limit)
        )
        return list(result)

    async def record(
        self,
        *,
        company_a_id: uuid.UUID,
        company_b_id: uuid.UUID,
        similarity: float,
        reason: str,
    ) -> None:
        """Queue a pair for review.

        The pair is stored in a fixed order and ignored if already queued, so
        re-running an ingest never fills the queue with the same two companies.
        """
        first, second = sorted([company_a_id, company_b_id], key=str)
        statement = insert(DuplicateCandidate).values(
            company_a_id=first,
            company_b_id=second,
            similarity=similarity,
            reason=reason,
            status=DuplicateStatus.PENDING,
        )
        await self.session.execute(statement.on_conflict_do_nothing(constraint="uq_duplicate_pair"))

    async def repoint(self, absorbed_id: uuid.UUID, kept_id: uuid.UUID) -> None:
        """Move any other pending pair from the absorbed company to the survivor.

        A pair that would then compare the survivor with itself is dropped: that
        question no longer exists.

        These are bulk statements with in-memory synchronisation switched off on
        purpose. Letting SQLAlchemy mirror them onto loaded objects is what once
        detached the pair being resolved and silently discarded its new status.
        """
        no_sync = {"synchronize_session": False}
        await self.session.execute(
            delete(DuplicateCandidate)
            .where(
                DuplicateCandidate.status == DuplicateStatus.PENDING,
                or_(
                    (DuplicateCandidate.company_a_id == kept_id)
                    & (DuplicateCandidate.company_b_id == absorbed_id),
                    (DuplicateCandidate.company_a_id == absorbed_id)
                    & (DuplicateCandidate.company_b_id == kept_id),
                ),
            )
            .execution_options(**no_sync)
        )

        # A pending pair between the absorbed company and X asks nothing new when the
        # survivor already has a pair with X, queued or decided: moving it across would
        # duplicate that pair, which the unique constraint refuses. A dentist paired
        # with both her practice and a colleague, merged into the practice, is the case.
        other = case(
            (DuplicateCandidate.company_a_id == absorbed_id, DuplicateCandidate.company_b_id),
            else_=DuplicateCandidate.company_a_id,
        )
        existing = aliased(DuplicateCandidate)
        already_asked = exists().where(
            existing.id != DuplicateCandidate.id,
            or_(
                (existing.company_a_id == kept_id) & (existing.company_b_id == other),
                (existing.company_b_id == kept_id) & (existing.company_a_id == other),
            ),
        )
        await self.session.execute(
            delete(DuplicateCandidate)
            .where(
                DuplicateCandidate.status == DuplicateStatus.PENDING,
                or_(
                    DuplicateCandidate.company_a_id == absorbed_id,
                    DuplicateCandidate.company_b_id == absorbed_id,
                ),
                already_asked,
            )
            .execution_options(**no_sync)
        )
        for column in (DuplicateCandidate.company_a_id, DuplicateCandidate.company_b_id):
            await self.session.execute(
                update(DuplicateCandidate)
                .where(column == absorbed_id, DuplicateCandidate.status == DuplicateStatus.PENDING)
                .values({column: kept_id})
                .execution_options(**no_sync)
            )
