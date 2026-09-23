"""Recording when each company's website domain was registered."""

from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from dealsignal.core.errors import ExternalServiceError
from dealsignal.core.logging import get_logger
from dealsignal.matching.merge import confidence_of
from dealsignal.models.company import Company
from dealsignal.models.enums import SourceName
from dealsignal.repositories.company import CompanyRepository
from dealsignal.repositories.field_value import FieldValueRepository
from dealsignal.sources.rdap import RdapSource, RegistrationOutcome

log = get_logger(__name__)

FIELD = "domain_registered_year"
SHARED_DOMAIN_REASON = "Several businesses list {domain}, so its age says nothing about this one."

NO_DATE_REASONS: dict[RegistrationOutcome, str] = {
    RegistrationOutcome.NO_SERVICE: "Registries for .{extension} domains do not publish dates.",
    RegistrationOutcome.NOT_REGISTERED: (
        "The registry has no record of {domain}, so the domain has probably lapsed."
    ),
    RegistrationOutcome.NO_DATE: "The registry for {domain} does not give a registration date.",
}


class DomainAgeOutcome(BaseModel):
    model_config = ConfigDict(frozen=True)

    company_id: str
    succeeded: bool
    message: str
    registered_year: int | None = None


class DomainAgeService:
    """Looks up and stores one company's domain registration year."""

    def __init__(
        self,
        session: AsyncSession,
        source: RdapSource,
        *,
        shared_domains: frozenset[str] | None = None,
    ) -> None:
        self._fields = FieldValueRepository(session)
        self._companies = CompanyRepository(session)
        self._source = source
        self._shared: frozenset[str] | None = shared_domains
        """Domains several companies list. Read from the database unless given."""

    async def enrich(self, company: Company) -> DomainAgeOutcome:
        if not company.domain:
            return self._outcome(company, False, "No website domain on record to look up.")
        if company.domain in await self._shared_domains():
            return self._outcome(company, False, SHARED_DOMAIN_REASON.format(domain=company.domain))

        try:
            answer = await self._source.lookup(company.domain)
        except ExternalServiceError as error:
            return self._outcome(company, False, error.message)

        registered = answer.registered
        if registered is None:
            reason = NO_DATE_REASONS[answer.outcome].format(
                domain=company.domain, extension=company.domain.rsplit(".", 1)[-1]
            )
            return self._outcome(company, False, reason)

        await self._fields.record(
            company_id=company.id,
            field=FIELD,
            value=registered.year,
            source=SourceName.RDAP,
            observed_at=datetime.now(UTC),
            confidence=confidence_of(SourceName.RDAP),
            evidence=f"{company.domain} registered {registered.isoformat()}",
        )
        return self._outcome(
            company, True, f"Domain registered {registered.isoformat()}.", registered.year
        )

    async def _shared_domains(self) -> frozenset[str]:
        """Read once per run: a job checks hundreds of companies."""
        if self._shared is None:
            self._shared = frozenset(await self._companies.shared_domains())
        return self._shared

    @staticmethod
    def _outcome(
        company: Company, succeeded: bool, message: str, year: int | None = None
    ) -> DomainAgeOutcome:
        if not succeeded:
            log.info("domain_age_skipped", company=company.display_name, reason=message)
        return DomainAgeOutcome(
            company_id=str(company.id), succeeded=succeeded, message=message, registered_year=year
        )
