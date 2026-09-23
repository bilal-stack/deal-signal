"""Turning place records into stored companies.

Three jobs, in order: clean the values, decide whether we already have this
business, then write it down with its provenance. Every count in the report is
real, including the ones that mean "we could not use this", because a silent drop
is how a tool ends up claiming eight results and showing none that fit.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from dealsignal.core.logging import get_logger
from dealsignal.matching.duplicates import Candidate, MatchDecision, compare
from dealsignal.matching.merge import confidence_of
from dealsignal.matching.normalize import normalize_name, normalize_phone, website_path
from dealsignal.matching.shared_domains import identity_domain
from dealsignal.models.company import Company
from dealsignal.models.enums import SourceName
from dealsignal.repositories.company import CompanyRepository
from dealsignal.repositories.duplicate import DuplicateRepository
from dealsignal.repositories.field_value import FieldValueRepository
from dealsignal.sources.base import PlaceRecord
from dealsignal.sources.industries import Industry

log = get_logger(__name__)


MAX_REPORTED_SKIPS = 20


class SkippedRecord(BaseModel):
    """A record the database refused, and why, in words a person can act on."""

    model_config = ConfigDict(frozen=True)

    name: str
    reason: str


class IngestReport(BaseModel):
    """What an ingest actually did. Shown to the user, not just logged."""

    model_config = ConfigDict(frozen=True)

    seen: int = 0
    created: int = 0
    merged: int = 0
    needs_review: int = 0
    skipped: int = 0
    skips: list[SkippedRecord] = []
    """Each skipped record and its reason, so a skip is never silent."""

    @property
    def stored(self) -> int:
        return self.created + self.merged


class CleanedPlace(BaseModel):
    """A place record after normalising, ready to compare and store."""

    model_config = ConfigDict(frozen=True)

    record: PlaceRecord
    normalized_name: str
    domain: str | None
    phone_e164: str | None

    def as_candidate(self) -> Candidate:
        return Candidate(
            name=self.record.name,
            domain=self.domain,
            phone_e164=self.phone_e164,
            latitude=self.record.latitude,
            longitude=self.record.longitude,
            website_path=website_path(self.record.website),
        )


def clean(record: PlaceRecord) -> CleanedPlace:
    """Normalise the fields duplicate detection and storage rely on."""
    return CleanedPlace(
        record=record,
        normalized_name=normalize_name(record.name),
        # A page on a shared host (a site builder, a directory, a franchise brand)
        # identifies nobody, so it gets no domain: see matching/shared_domains.py.
        domain=identity_domain(record.website),
        phone_e164=normalize_phone(record.phone, country=record.country),
    )


class PlaceIngestService:
    """Stores place records, merging them into companies we already know."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._companies = CompanyRepository(session)
        self._fields = FieldValueRepository(session)
        self._duplicates = DuplicateRepository(session)

    async def ingest(self, records: Iterable[PlaceRecord], *, industry: Industry) -> IngestReport:
        seen = created = merged = needs_review = skipped = 0
        skips: list[SkippedRecord] = []

        for record in records:
            seen += 1
            try:
                # One savepoint per record: a record the database refuses is rolled
                # back on its own, instead of taking the whole batch down with it.
                async with self._session.begin_nested():
                    was_created, queued = await self._ingest_one(record, industry)
            except IntegrityError as exc:
                skipped += 1
                if len(skips) < MAX_REPORTED_SKIPS:
                    skips.append(SkippedRecord(name=record.name, reason=self._explain(exc)))
                log.warning("ingest_record_skipped", name=record.name, error=str(exc.orig))
                continue

            created += int(was_created)
            merged += int(not was_created)
            needs_review += queued

        report = IngestReport(
            seen=seen,
            created=created,
            merged=merged,
            needs_review=needs_review,
            skipped=skipped,
            skips=skips,
        )
        log.info("ingest_complete", industry=industry.key, **report.model_dump())
        return report

    async def _ingest_one(self, record: PlaceRecord, industry: Industry) -> tuple[bool, int]:
        """Store one record. Returns (created a new company?, pairs queued for review)."""
        cleaned = clean(record)
        existing, review_pairs = await self._find_existing(cleaned)

        if existing is None:
            company = self._create(cleaned, industry)
        else:
            company = existing
            if industry.key not in (company.industry_keys or []):
                # A plumber that also lists HVAC services belongs to both searches.
                company.industry_keys = [*(company.industry_keys or []), industry.key]

        await self._session.flush()
        await self._record_provenance(company, cleaned)

        # Uncertain pairs go to a queue a person can act on, rather than being
        # merged on a guess or dropped without trace.
        queued = 0
        for other, decision in review_pairs:
            if other.id == company.id:
                continue
            await self._duplicates.record(
                company_a_id=company.id,
                company_b_id=other.id,
                similarity=decision.score,
                reason=decision.reason,
            )
            queued += 1
        return existing is None, queued

    @staticmethod
    def _explain(exc: IntegrityError) -> str:
        """A readable reason, without leaking a database stack trace to the user."""
        log.debug("ingest_integrity_error", error=str(exc.orig))
        return "the database refused this record"

    async def _find_existing(
        self, cleaned: CleanedPlace
    ) -> tuple[Company | None, list[tuple[Company, MatchDecision]]]:
        """The company this record belongs to, plus any pairs worth a human look."""
        candidates = await self._companies.find_duplicate_candidates(
            normalized_name=cleaned.normalized_name,
            domain=cleaned.domain,
            phone_e164=cleaned.phone_e164,
            latitude=cleaned.record.latitude,
            longitude=cleaned.record.longitude,
        )
        if not candidates:
            return None, []

        incoming = cleaned.as_candidate()
        places = await self._companies.coordinates([company.id for company in candidates])
        best_match: Company | None = None
        best_score = 0.0
        to_review: list[tuple[Company, MatchDecision]] = []

        for company in candidates:
            latitude, longitude = places.get(company.id, (None, None))
            decision = compare(
                incoming,
                Candidate(
                    name=company.display_name,
                    domain=company.domain,
                    phone_e164=company.phone_e164,
                    latitude=latitude,
                    longitude=longitude,
                    website_path=website_path(company.website_url),
                ),
            )
            if decision.merge and decision.score > best_score:
                best_match, best_score = company, decision.score
            elif decision.review:
                to_review.append((company, decision))

        # A confident merge answers the question, so nothing is left to review.
        return best_match, [] if best_match else to_review

    def _create(self, cleaned: CleanedPlace, industry: Industry) -> Company:
        """A new company row, holding only what the source actually provided."""
        record = cleaned.record
        company = Company(
            display_name=record.name,
            normalized_name=cleaned.normalized_name,
            domain=cleaned.domain,
            website_url=record.website,
            phone_e164=cleaned.phone_e164,
            street=record.street,
            city=record.city,
            region=record.region,
            postal_code=record.postal_code,
            country=record.country,
            industry_code=industry.naics,
            industry_label=industry.label,
            industry_keys=[industry.key],
            geo=self._point(record.latitude, record.longitude),
        )
        return self._companies.add(company)

    async def _record_provenance(self, company: Company, cleaned: CleanedPlace) -> None:
        """Write down what this source said about each field, and when."""
        observed_at = datetime.now(UTC)
        source: SourceName = cleaned.record.source
        values: dict[str, object | None] = {
            "display_name": cleaned.record.name,
            "domain": cleaned.domain,
            "phone_e164": cleaned.phone_e164,
            "street": cleaned.record.street,
            "city": cleaned.record.city,
            "postal_code": cleaned.record.postal_code,
            "category": cleaned.record.category,
        }
        for field, value in values.items():
            if value in (None, ""):
                continue
            await self._fields.record(
                company_id=company.id,
                field=field,
                value=value,
                source=source,
                observed_at=observed_at,
                confidence=confidence_of(source),
            )

    @staticmethod
    def _point(latitude: float | None, longitude: float | None) -> str | None:
        """PostGIS point literal, or None when the source gave no coordinates."""
        if latitude is None or longitude is None:
            return None
        return f"SRID=4326;POINT({longitude} {latitude})"
