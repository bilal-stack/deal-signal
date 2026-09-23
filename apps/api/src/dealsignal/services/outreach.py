"""Preparing the facts a draft is built from, and refusing when we should not write.

The value here is not the model call. It is that the sender never has to type what
the company does, how long it has traded or who owns it: the system already knows,
and every line it gives the model is something it can show a source for.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable

from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from dealsignal.ai.outreach import OutreachDraft, OutreachWriter
from dealsignal.core.errors import ConflictError, NotFoundError
from dealsignal.core.logging import get_logger
from dealsignal.models.buy_box import BuyBox
from dealsignal.models.company import Company
from dealsignal.models.enums import SourceName
from dealsignal.repositories.company import CompanyRepository
from dealsignal.repositories.field_value import FieldValueRepository
from dealsignal.repositories.person import PersonRepository
from dealsignal.repositories.suppression import SuppressionRepository
from dealsignal.services.facts import best_by_field, primary_owner

log = get_logger(__name__)

QUOTABLE_FACTS: tuple[str, ...] = (
    "mentions_family_ownership",
    "has_recurring_revenue",
    "sells_to_businesses",
)
"""Things a business says about itself that make a fair, specific opening."""

SOURCE_WORDS: dict[str, str] = {
    SourceName.WEBSITE: "their website",
    SourceName.RECHERCHE_ENTREPRISES: "the French company register",
    SourceName.COMPANIES_HOUSE: "Companies House",
}


class SenderProfile(BaseModel):
    """Who is writing, in their own words."""

    model_config = ConfigDict(frozen=True)

    name: str
    background: str
    """One or two lines: who they are and what they are looking for."""


class DraftResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    company_id: str
    company_name: str
    draft: OutreachDraft
    facts_used: list[str]
    """Shown next to the draft, so every claim in it can be checked."""


class OutreachService:
    """Builds the brief, refuses blocked companies, and returns a draft."""

    def __init__(self, session: AsyncSession, writer: Callable[[], OutreachWriter]) -> None:
        self._companies = CompanyRepository(session)
        self._people = PersonRepository(session)
        self._fields = FieldValueRepository(session)
        self._suppression = SuppressionRepository(session)
        self._writer = writer
        """A factory, not an instance: a blocked company must be refused before any
        model client is built, so a missing key never masks the real reason."""

    async def draft(
        self, company_id: uuid.UUID, sender: SenderProfile, buy_box: BuyBox | None = None
    ) -> DraftResult:
        company = await self._companies.get(company_id)
        if company is None:
            raise NotFoundError(f"No company with id {company_id}.")

        blocked = await self._suppression.matching(company)
        if blocked is not None:
            raise ConflictError(
                f"{company.display_name} is on the do-not-contact list"
                + (f": {blocked.reason}" if blocked.reason else "."),
                details={"suppression_id": str(blocked.id)},
            )

        facts = await self._gather_facts(company)
        purpose = str(buy_box.mode) if buy_box is not None else "acquisition"

        draft = await self._writer().write(
            company=self._describe(company),
            facts="\n".join(f"- {fact}" for fact in facts) or "- Nothing beyond the name.",
            sender=f"{sender.name}. {sender.background}",
            purpose=purpose,
        )
        log.info("outreach_drafted", company=company.display_name, facts=len(facts))
        return DraftResult(
            company_id=str(company.id),
            company_name=company.display_name,
            draft=draft,
            facts_used=facts,
        )

    @staticmethod
    def _describe(company: Company) -> str:
        where = ", ".join(part for part in (company.city, company.region) if part)
        return f"{company.display_name}" + (f" ({where})" if where else "")

    async def _gather_facts(self, company: Company) -> list[str]:
        """Public facts the message may mention, each saying where it came from.

        Private context stays out on purpose. The owner's age, our revenue estimate and
        the score's reasons help a buyer decide whom to contact, but a first message
        that hints at them reads as surveillance, not interest.
        """
        facts: list[str] = []
        if company.summary:
            facts.append(f"What they do: {company.summary}")
        elif company.industry_label:
            facts.append(f"Industry: {company.industry_label}")

        known = best_by_field(await self._fields.all_for_company(company.id))
        founded = known.get("founded_year")
        if founded is not None:
            facts.append(f"Founded in {founded.value}, according to {source_words(founded.source)}")
        for field in QUOTABLE_FACTS:
            found = known.get(field)
            if found is not None and found.value is True and found.evidence:
                facts.append(f'Their website says: "{found.evidence}"')
        if company.employee_count:
            facts.append(f"About {company.employee_count} staff, as their website states")

        owner = primary_owner(await self._people.for_company(company.id))
        if owner is not None:
            role = f", {owner.role}" if owner.role else ""
            facts.append(f"Named on the public company register: {owner.full_name}{role}")
        return facts


def source_words(source: str) -> str:
    return SOURCE_WORDS.get(source, str(source))
