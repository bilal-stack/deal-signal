"""The duplicate review queue.

Pairs the matcher was not sure about, and the two decisions a person can make:
they are the same business, or they are not.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Query

from dealsignal.core.deps import SessionDep
from dealsignal.schemas.duplicate import DuplicatePair, DuplicateSide, ResolveResult
from dealsignal.services.duplicate_resolution import DuplicateResolver, Side

router = APIRouter(prefix="/duplicates", tags=["duplicates"])

DEFAULT_LIMIT = 50
MAX_LIMIT = 200


@router.get("", response_model=list[DuplicatePair])
async def list_duplicates(
    session: SessionDep,
    limit: int = Query(default=DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
) -> list[DuplicatePair]:
    """Pairs waiting on a decision, most similar first."""
    pairs = await DuplicateResolver(session).pending_pairs(limit=limit)
    return [
        DuplicatePair(
            id=candidate.id,
            similarity=candidate.similarity,
            reason=candidate.reason,
            left=DuplicateSide.from_company(left),
            right=DuplicateSide.from_company(right),
        )
        for candidate, left, right in pairs
    ]


@router.post("/{candidate_id}/merge", response_model=ResolveResult)
async def merge_pair(
    candidate_id: uuid.UUID,
    session: SessionDep,
    keep: Annotated[Side, Query(description="Whose name and details survive: a or b.")] = "a",
) -> ResolveResult:
    """They are the same business: fold one record into the other.

    Committed here, before the response, so a failure is reported as a failure
    rather than a 200 over a write that later rolls back.
    """
    resolution = await DuplicateResolver(session).merge(candidate_id, keep=keep)
    await session.commit()
    return ResolveResult.from_resolution(resolution)


@router.post("/{candidate_id}/reject", response_model=ResolveResult)
async def reject_pair(candidate_id: uuid.UUID, session: SessionDep) -> ResolveResult:
    """They are different businesses: leave both and stop asking."""
    resolution = await DuplicateResolver(session).reject(candidate_id)
    await session.commit()
    return ResolveResult.from_resolution(resolution)
