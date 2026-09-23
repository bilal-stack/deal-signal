"""Running a Buy Box against the companies we hold.

Two steps: a cheap database filter on country, industry and town, then the scorer
on each survivor. The filter deliberately does little, because the criteria that
matter (owner age, revenue band, repeat revenue) live in facts the query cannot
see.
"""

from __future__ import annotations

import uuid

from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from dealsignal.core.errors import ValidationError
from dealsignal.core.logging import get_logger
from dealsignal.models.buy_box import BuyBox
from dealsignal.models.enums import Country
from dealsignal.repositories.company import CompanyRepository
from dealsignal.repositories.suppression import SuppressionRepository
from dealsignal.services.scoring_service import ScoredCompany, ScoringService
from dealsignal.sources.industries import resolve, supported_labels

log = get_logger(__name__)

DEFAULT_SEARCH_LIMIT = 200


class SearchOutcome(BaseModel):
    """What a search found, and what it could not judge."""

    model_config = ConfigDict(frozen=True)

    buy_box_id: str
    considered: int
    scored: list[ScoredCompany]
    withheld: int = 0
    """On the do-not-contact list, so left out of the results and every export."""

    @property
    def high_confidence(self) -> int:
        return sum(1 for item in self.scored if item.result.confidence_label == "high")


class SearchService:
    """Finds and ranks the companies that match a Buy Box."""

    def __init__(self, session: AsyncSession, scoring: ScoringService | None = None) -> None:
        self._companies = CompanyRepository(session)
        self._suppression = SuppressionRepository(session)
        self._scoring = scoring or ScoringService(session)

    async def run(self, buy_box: BuyBox, *, limit: int = DEFAULT_SEARCH_LIMIT) -> SearchOutcome:
        keys = self._industry_keys(buy_box.industries)
        countries = [Country(code) for code in buy_box.countries]

        found = await self._companies.search(
            countries=countries, industry_keys=keys, city=buy_box.city, limit=limit
        )

        # Anything on the do-not-contact list leaves here, so it cannot reach a
        # results table, an export or a draft.
        blocked = await self._suppression.blocked(found)
        companies = [company for company in found if company.id not in blocked]

        scored = [await self._scoring.score_company(company, buy_box) for company in companies]
        positions = await self._companies.coordinates([company.id for company in companies])
        scored = [self._with_position(item, positions) for item in scored]

        scored.sort(
            key=lambda item: (item.result.score is not None, item.result.score or 0),
            reverse=True,
        )

        log.info(
            "search_complete",
            buy_box=buy_box.name,
            considered=len(companies),
            withheld=len(blocked),
        )
        return SearchOutcome(
            buy_box_id=str(buy_box.id),
            considered=len(companies),
            scored=scored,
            withheld=len(blocked),
        )

    @staticmethod
    def _with_position(
        item: ScoredCompany, positions: dict[uuid.UUID, tuple[float, float]]
    ) -> ScoredCompany:
        """Attach a map position when the company has one; leave it unknown otherwise."""
        position = positions.get(uuid.UUID(item.company_id))
        if position is None:
            return item
        latitude, longitude = position
        return item.model_copy(update={"latitude": latitude, "longitude": longitude})

    @staticmethod
    def _industry_keys(industries: list[str]) -> list[str]:
        """Turn the Buy Box's industry names into our industry keys, refusing unknown ones.

        Saying "we do not cover that" is better than silently returning whatever
        happens to match, which is how a search for HVAC ends up full of lumber.
        """
        keys: list[str] = []
        unknown: list[str] = []
        for name in industries:
            industry = resolve(name)
            if industry is None:
                unknown.append(name)
            else:
                keys.append(industry.key)

        if unknown:
            raise ValidationError(
                f"These industries are not supported yet: {', '.join(unknown)}. "
                f"Supported: {', '.join(supported_labels())}.",
                details={"unsupported": unknown},
            )
        return keys
