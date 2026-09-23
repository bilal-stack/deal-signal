"""Buy Box and score storage."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from dealsignal.models.buy_box import BuyBox, Score
from dealsignal.repositories.base import BaseRepository


class BuyBoxRepository(BaseRepository[BuyBox]):
    model = BuyBox

    async def recent(self, *, limit: int) -> list[BuyBox]:
        """Newest first: the one just saved is the one most likely wanted again."""
        result = await self.session.scalars(
            select(BuyBox).order_by(BuyBox.created_at.desc()).limit(limit)
        )
        return list(result)


class ScoreRepository(BaseRepository[Score]):
    model = Score

    async def upsert(
        self,
        *,
        company_id: uuid.UUID,
        buy_box_id: uuid.UUID,
        score: float | None,
        confidence: float,
        reasons: list[dict[str, object]],
        computed_at: datetime,
    ) -> None:
        """Rescoring a company replaces its previous score for that Buy Box."""
        statement = insert(Score).values(
            company_id=company_id,
            buy_box_id=buy_box_id,
            score=score,
            confidence=confidence,
            reasons=reasons,
            computed_at=computed_at,
        )
        await self.session.execute(
            statement.on_conflict_do_update(
                index_elements=[Score.company_id, Score.buy_box_id],
                set_={
                    "score": statement.excluded.score,
                    "confidence": statement.excluded.confidence,
                    "reasons": statement.excluded.reasons,
                    "computed_at": statement.excluded.computed_at,
                },
            )
        )
