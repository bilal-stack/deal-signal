"""Scoring stored companies against a Buy Box.

The scorer itself is pure. This service is the part that knows where facts live:
it gathers them, runs the signals, and saves the result with its reasons intact.
"""

from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from dealsignal.core.logging import get_logger
from dealsignal.models.buy_box import BuyBox
from dealsignal.models.company import Company
from dealsignal.repositories.buy_box import ScoreRepository
from dealsignal.repositories.company import CompanyRepository
from dealsignal.repositories.field_value import FieldValueRepository
from dealsignal.repositories.person import PersonRepository
from dealsignal.scoring.context import BuyBoxCriteria, ScoringContext
from dealsignal.scoring.scorer import Scorer, ScoreResult
from dealsignal.scoring.signals import signals_for
from dealsignal.services.facts import best_by_field, build_company_facts

log = get_logger(__name__)

DOMAIN_AGE_FACT = "domain_registered_year"

STORED_FACT_TO_SCORING_FACT: dict[str, str] = {
    "has_recurring_revenue": "has_recurring_revenue",
    "sells_to_businesses": "sells_to_businesses",
    "mentions_family_ownership": "mentions_family_ownership",
    "is_part_of_group": "has_parent_company",
    "location_count": "location_count",
    "website_last_updated_year": "website_last_updated_year",
    "review_count": "review_count",
    "review_growth_ratio": "review_growth_ratio",
    "domain_registered_year": "domain_registered_year",
}
"""Facts that live in field_values rather than on the company row. The website
reader calls one of them is_part_of_group; scoring asks has_parent_company."""

EVIDENCE_FOR_ROW_FACTS: dict[str, str] = {
    "founded_year": "founded_year",
    "employee_count": "employee_count",
    "employee_band": "employee_count",
    "revenue_estimate": "revenue",
}
"""Facts whose value is on the company row but whose sentence or method is kept with
the field value. Earlier entries win, so a stated headcount beats a register band.
Evidence is keyed by the fact a signal reads, and "revenue" for the revenue range."""


class ScoredCompany(BaseModel):
    """A company with its score, ready for the results table."""

    model_config = ConfigDict(frozen=True)

    company_id: str
    name: str
    result: ScoreResult
    latitude: float | None = None
    longitude: float | None = None


class ScoringService:
    """Scores companies and stores the result."""

    def __init__(self, session: AsyncSession, scorer: Scorer | None = None) -> None:
        self._session = session
        self._scorer_override = scorer
        self._fields = FieldValueRepository(session)
        self._scores = ScoreRepository(session)
        self._people = PersonRepository(session)
        self._companies = CompanyRepository(session)
        self._shared: set[str] | None = None

    async def score_company(self, company: Company, buy_box: BuyBox) -> ScoredCompany:
        """Score one company, saving the score and the reasons behind it."""
        # People are fetched explicitly. Reading `company.people` depended on every
        # caller having eager-loaded them, and a lazy load in async code crashes.
        facts = build_company_facts(
            company,
            people=await self._people.for_company(company.id),
            extra=await self._extra_facts(company),
        )
        criteria = BuyBoxCriteria(
            revenue_min=buy_box.revenue_min,
            revenue_max=buy_box.revenue_max,
            employees_min=buy_box.employees_min,
            employees_max=buy_box.employees_max,
            exclude_pe_owned=buy_box.exclude_pe_owned,
            weights={key: int(value) for key, value in (buy_box.weights or {}).items()},
        )

        scorer = self._scorer_override or Scorer(signals_for(buy_box.mode))
        result = scorer.score(ScoringContext(facts=facts, criteria=criteria))

        await self._scores.upsert(
            company_id=company.id,
            buy_box_id=buy_box.id,
            score=result.score,
            confidence=result.confidence,
            reasons=[reason.model_dump() for reason in result.reasons],
            computed_at=datetime.now(UTC),
        )
        return ScoredCompany(company_id=str(company.id), name=company.display_name, result=result)

    async def _extra_facts(self, company: Company) -> dict[str, object]:
        """Facts recorded by other sources, with their evidence quotes."""
        gathered: dict[str, object] = {}
        evidence: dict[str, str] = {}
        recorded = best_by_field(await self._fields.all_for_company(company.id))

        for stored_field, fact_name in STORED_FACT_TO_SCORING_FACT.items():
            best = recorded.get(stored_field)
            if best is None:
                continue
            gathered[fact_name] = best.value
            if best.evidence:
                evidence[fact_name] = best.evidence

        for stored_field, fact_name in EVIDENCE_FOR_ROW_FACTS.items():
            best = recorded.get(stored_field)
            if best is not None and best.evidence and fact_name not in evidence:
                evidence[fact_name] = best.evidence

        if not await self._owns_its_domain(company):
            # A date for a domain this company does not own (a shared host, or one
            # several businesses list) says nothing about how long it has traded.
            gathered.pop(DOMAIN_AGE_FACT, None)
            evidence.pop(DOMAIN_AGE_FACT, None)

        if evidence:
            gathered["evidence"] = evidence
        return gathered

    async def _owns_its_domain(self, company: Company) -> bool:
        if not company.domain:
            return False
        if self._shared is None:
            self._shared = await self._companies.shared_domains()
        return company.domain not in self._shared
