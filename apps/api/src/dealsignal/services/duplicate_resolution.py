"""Acting on a review decision.

The order of operations matters:

1. Record the decision first, so no later bulk statement can match this pair.
2. Re-point the absorbed company's other pairs to the survivor before it is deleted;
   its foreign key would otherwise null them and drop them from the queue.
3. Only then merge the companies.
"""

from __future__ import annotations

import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from dealsignal.core.errors import ConflictError
from dealsignal.core.logging import get_logger
from dealsignal.models.company import Company
from dealsignal.models.duplicate import DuplicateCandidate
from dealsignal.models.enums import DuplicateStatus
from dealsignal.repositories.company import CompanyRepository
from dealsignal.repositories.duplicate import DuplicateRepository
from dealsignal.services.merge_companies import CompanyMerger

log = get_logger(__name__)


class Resolution(BaseModel):
    """What happened to a pair, in the words the reviewer sees."""

    model_config = ConfigDict(frozen=True)

    candidate_id: uuid.UUID
    status: DuplicateStatus
    message: str
    company_id: uuid.UUID | None = None


Side = Literal["a", "b"]
"""Which record of a pair: the first (a) or the second (b)."""


class DuplicateResolver:
    """Applies a reviewer's decision to a pair of possible duplicates."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._duplicates = DuplicateRepository(session)
        self._companies = CompanyRepository(session)
        self._merger = CompanyMerger(session)

    async def pending_pairs(
        self, *, limit: int
    ) -> list[tuple[DuplicateCandidate, Company, Company]]:
        """Pairs waiting on a decision, most similar first, with both companies."""
        candidates = await self._duplicates.pending(limit=limit)
        ids = {c.company_a_id for c in candidates} | {
            c.company_b_id for c in candidates if c.company_b_id
        }
        companies = await self._companies.by_ids(list(ids))
        return [
            (candidate, companies[candidate.company_a_id], companies[candidate.company_b_id])
            for candidate in candidates
            if candidate.company_b_id
            and candidate.company_a_id in companies
            and candidate.company_b_id in companies
        ]

    async def merge(self, candidate_id: uuid.UUID, *, keep: Side = "a") -> Resolution:
        """The two records are one business: fold one into the other.

        `keep` is the record whose name and details survive. A reviewer keeps the
        practice rather than one of its dentists, the full name rather than an acronym.
        """
        candidate = await self._duplicates.get_or_raise(candidate_id)
        if candidate.status != DuplicateStatus.PENDING or candidate.company_b_id is None:
            raise ConflictError("This pair has already been merged.")

        kept_id, absorbed_id = candidate.company_a_id, candidate.company_b_id
        if keep == "b":
            kept_id, absorbed_id = absorbed_id, kept_id

        candidate.status = DuplicateStatus.MERGED
        # The decision points at the survivor: the absorbed company is about to be
        # deleted, and the pair's first company is a cascading foreign key.
        candidate.company_a_id = kept_id
        candidate.company_b_id = None
        await self._session.flush()

        await self._duplicates.repoint(absorbed_id, kept_id)
        kept = await self._merger.merge(kept_id, absorbed_id)

        log.info("duplicate_merged", candidate=str(candidate_id), kept=str(kept_id))
        return Resolution(
            candidate_id=candidate.id,
            status=DuplicateStatus.MERGED,
            message=f"Merged into {kept.display_name}.",
            company_id=kept.id,
        )

    async def reject(self, candidate_id: uuid.UUID) -> Resolution:
        """The two records are different businesses: keep both, stop asking."""
        candidate = await self._duplicates.get_or_raise(candidate_id)
        if candidate.status != DuplicateStatus.PENDING:
            raise ConflictError("This pair has already been decided.")

        candidate.status = DuplicateStatus.REJECTED
        await self._session.flush()

        return Resolution(
            candidate_id=candidate.id,
            status=DuplicateStatus.REJECTED,
            message="Kept as two separate companies.",
        )
