"""Enriching one company from its own website.

Fetch, read, then write down what was learned with the evidence attached. Each
step can fail on its own terms, and a failure is reported rather than folded into
a half-empty record: the caller gets an outcome that says what happened.
"""

from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from dealsignal.ai.extractor import WebsiteExtractor
from dealsignal.ai.schemas import WebsiteFacts
from dealsignal.core.errors import ExternalServiceError, SourceBlockedError
from dealsignal.core.logging import get_logger
from dealsignal.matching.merge import confidence_of
from dealsignal.models.company import Company
from dealsignal.models.enums import SourceName
from dealsignal.repositories.field_value import FieldValueRepository
from dealsignal.services.estimates import record_revenue_estimate
from dealsignal.sources.website import WebsiteReader

log = get_logger(__name__)

WEBSITE_FIELDS_TO_COMPANY: frozenset[str] = frozenset({"founded_year", "employee_count"})
"""Extracted fields that are also columns on the company row. Everything else
stays a recorded fact that scoring reads, which keeps the table narrow."""


class EnrichmentOutcome(BaseModel):
    """What happened, in words a user can read."""

    model_config = ConfigDict(frozen=True)

    company_id: str
    succeeded: bool
    message: str
    facts: WebsiteFacts | None = None
    pages_read: int = 0
    last_copyright_year: int | None = None

    @property
    def learned_fields(self) -> list[str]:
        return sorted(self.facts.known_fields()) if self.facts else []


class WebsiteEnrichmentService:
    """Reads a company's website and records what it says."""

    def __init__(
        self,
        session: AsyncSession,
        reader: WebsiteReader,
        extractor: WebsiteExtractor,
    ) -> None:
        self._session = session
        self._reader = reader
        self._extractor = extractor
        self._fields = FieldValueRepository(session)

    async def enrich(self, company: Company) -> EnrichmentOutcome:
        """Read the site, or explain why we could not."""
        if not company.website_url:
            return self._failure(company, "This company has no website on record to read.")

        try:
            content = await self._reader.read(company.website_url)
        except SourceBlockedError as blocked:
            return self._failure(company, blocked.message)
        except ExternalServiceError as error:
            return self._failure(company, error.message)

        if not content.has_text:
            return self._failure(company, "The website had no readable text on it.")

        try:
            facts = await self._extractor.extract(
                company_name=company.display_name,
                url=company.website_url,
                pages=content.pages,
            )
        except ExternalServiceError as error:
            return self._failure(company, error.message)

        await self._store(company, facts, last_copyright_year=content.last_copyright_year)

        return EnrichmentOutcome(
            company_id=str(company.id),
            succeeded=True,
            message=f"Read {len(content.pages)} pages.",
            facts=facts,
            pages_read=len(content.pages),
            last_copyright_year=content.last_copyright_year,
        )

    async def _store(
        self, company: Company, facts: WebsiteFacts, *, last_copyright_year: int | None
    ) -> None:
        """Save each fact with the sentence that supports it."""
        observed_at = datetime.now(UTC)
        confidence = confidence_of(SourceName.WEBSITE)

        for field, value in facts.known_fields().items():
            await self._fields.record(
                company_id=company.id,
                field=field,
                value=value,
                source=SourceName.WEBSITE,
                observed_at=observed_at,
                confidence=confidence,
                evidence=facts.quote_for(field),
            )
            if field in WEBSITE_FIELDS_TO_COMPANY and getattr(company, field) is None:
                setattr(company, field, value)

        await record_revenue_estimate(company, self._fields, observed_at=observed_at)

        if last_copyright_year is not None:
            await self._fields.record(
                company_id=company.id,
                field="website_last_updated_year",
                value=last_copyright_year,
                source=SourceName.WEBSITE,
                observed_at=observed_at,
                confidence=confidence,
                evidence=None,
            )

        company.summary = facts.summary

    @staticmethod
    def _failure(company: Company, message: str) -> EnrichmentOutcome:
        """A failure the user can read, never a silent empty success."""
        log.info("enrichment_failed", company=company.display_name, reason=message)
        return EnrichmentOutcome(company_id=str(company.id), succeeded=False, message=message)
