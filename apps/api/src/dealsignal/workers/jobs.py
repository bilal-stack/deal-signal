"""Background jobs.

Each job opens its own transaction, does one kind of work, and returns a JobReport
that is stored as the job's result. The UI polls for that report, which is how a
button click turns into something the user can see finish, or see fail and why.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from dealsignal.ai.extractor import WebsiteExtractor
from dealsignal.core.cache import open_cache
from dealsignal.core.config import get_settings
from dealsignal.core.errors import DealSignalError
from dealsignal.core.logging import get_logger
from dealsignal.db.session import session_scope
from dealsignal.models.company import Company
from dealsignal.models.enums import Country, EnrichmentTask
from dealsignal.repositories.company import CompanyRepository
from dealsignal.repositories.enrichment_attempt import EnrichmentAttemptRepository
from dealsignal.services.domain_age import FIELD as DOMAIN_AGE_FIELD
from dealsignal.services.domain_age import DomainAgeService
from dealsignal.services.enrichment import WebsiteEnrichmentService
from dealsignal.services.ingest import PlaceIngestService
from dealsignal.services.registry_enrichment import RegistryEnrichmentService
from dealsignal.sources.companies_house import CompaniesHouseSource
from dealsignal.sources.industries import resolve, supported_labels
from dealsignal.sources.overture import OverturePlacesSource
from dealsignal.sources.rdap import RdapSource
from dealsignal.sources.recherche_entreprises import RechercheEntreprisesSource
from dealsignal.sources.regions import get_region
from dealsignal.sources.website import WebsiteReader
from dealsignal.workers.batch import Failure, JobReport, Outcome, run_batch

log = get_logger(__name__)

REGISTER_PAUSE_SECONDS = 0.3


def _report(report: JobReport) -> dict[str, Any]:
    """arq stores results as plain data."""
    return report.model_dump()


async def seed_region(
    ctx: dict[str, Any], region: str, industry: str, limit: int
) -> dict[str, Any]:
    """Load companies for one region and industry from open data."""
    resolved = resolve(industry)
    if resolved is None:
        return _report(
            JobReport(
                job="seed_region",
                note=f"{industry!r} is not supported. Try: {', '.join(supported_labels())}.",
            )
        )

    place = get_region(region)
    try:
        records = await OverturePlacesSource(get_settings()).search(
            industry=resolved, region=place, limit=limit
        )
    except DealSignalError as error:
        return _report(JobReport(job="seed_region", note=error.message))

    async with session_scope() as session:
        result = await PlaceIngestService(session).ingest(records, industry=resolved)

    return _report(
        JobReport(
            job="seed_region",
            attempted=result.seen,
            succeeded=result.stored,
            failures=[Failure(company=skip.name, reason=skip.reason) for skip in result.skips],
            note=(
                f"{place.label}, {resolved.label}: {result.created} new, {result.merged} merged, "
                f"{result.needs_review} sent to the review queue"
                + (f", {result.skipped} skipped." if result.skipped else ".")
            ),
        )
    )


async def lookup_registry(ctx: dict[str, Any], country: str, limit: int) -> dict[str, Any]:
    """Match companies to their national register."""
    settings = get_settings()
    sources = [RechercheEntreprisesSource(settings), CompaniesHouseSource(settings)]

    async with session_scope() as session:
        service = RegistryEnrichmentService(session, sources)
        wanted = Country(country)
        if service.source_for(wanted) is None:
            return _report(
                JobReport(
                    job="lookup_registry",
                    note=(
                        f"No free public register covers {wanted}. The UK and France are supported."
                    ),
                )
            )
        companies = await CompanyRepository(session).needing_register_lookup(wanted, limit=limit)
        report = await run_batch(
            "lookup_registry",
            companies,
            service.enrich,
            record=_remember(session, EnrichmentTask.REGISTRY),
            after_each=session.commit,
            pause_seconds=REGISTER_PAUSE_SECONDS,
        )
    return _report(report)


async def check_domain_age(ctx: dict[str, Any], limit: int) -> dict[str, Any]:
    """Record when each company's website domain was registered."""
    cache = await open_cache(get_settings())
    try:
        async with session_scope() as session:
            companies = await CompanyRepository(session).needing_field(
                DOMAIN_AGE_FIELD, task=EnrichmentTask.DOMAIN_AGE, limit=limit, require_domain=True
            )
            service = DomainAgeService(session, RdapSource(get_settings(), cache=cache))
            report = await run_batch(
                "check_domain_age",
                companies,
                service.enrich,
                record=_remember(session, EnrichmentTask.DOMAIN_AGE),
                after_each=session.commit,
            )
    finally:
        await cache.close()
    return _report(report)


async def read_websites(ctx: dict[str, Any], limit: int) -> dict[str, Any]:
    """Read company websites with Claude. Says so plainly when no key is configured."""
    settings = get_settings()
    try:
        extractor = WebsiteExtractor(settings)
    except DealSignalError as error:
        return _report(JobReport(job="read_websites", note=error.message))

    cache = await open_cache(settings)
    try:
        async with session_scope() as session:
            companies = await CompanyRepository(session).needing_website_read(limit=limit)
            reader = WebsiteReader(settings, cache=cache)
            service = WebsiteEnrichmentService(session, reader, extractor)
            report = await run_batch(
                "read_websites",
                companies,
                service.enrich,
                record=_remember(session, EnrichmentTask.WEBSITE),
                after_each=session.commit,
            )
    finally:
        await cache.close()
    return _report(report)


def _remember(
    session: AsyncSession, task: EnrichmentTask
) -> Callable[[Company, Outcome], Awaitable[None]]:
    """Record each attempt, so the next run starts with companies not yet tried."""
    attempts = EnrichmentAttemptRepository(session)

    async def remember(company: Company, outcome: Outcome) -> None:
        await attempts.record(
            company.id, task, succeeded=outcome.succeeded, message=outcome.message
        )

    return remember


JOBS = (seed_region, lookup_registry, check_domain_age, read_websites)
