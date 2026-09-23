"""Company queries.

Only the queries that are specific to companies live here; the plain CRUD comes
from `BaseRepository`. Duplicate detection needs three cheap lookups (domain,
phone, nearby-and-similar-name), so they are written once, here.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from geoalchemy2 import Geometry
from geoalchemy2.functions import ST_X, ST_Y, ST_DWithin, ST_MakePoint, ST_SetSRID
from sqlalchemy import Select, cast, exists, func, or_, select
from sqlalchemy.orm import selectinload

from dealsignal.models.company import Company
from dealsignal.models.enrichment import EnrichmentAttempt
from dealsignal.models.enums import Country, EnrichmentTask
from dealsignal.models.source import FieldValue
from dealsignal.repositories.base import BaseRepository

WGS84 = 4326
NEARBY_METRES = 150
NAME_SIMILARITY_THRESHOLD = 0.4
MAX_DUPLICATE_CANDIDATES = 25


class CompanyRepository(BaseRepository[Company]):
    model = Company

    async def shared_domains(self) -> set[str]:
        """Domains more than one company lists. Their age dates none of them."""
        result = await self.session.scalars(
            select(Company.domain)
            .where(Company.domain.is_not(None))
            .group_by(Company.domain)
            .having(func.count() > 1)
        )
        return {domain for domain in result if domain}

    async def search(
        self,
        *,
        countries: Sequence[Country],
        industry_keys: Sequence[str] = (),
        city: str | None = None,
        limit: int = 200,
        offset: int = 0,
    ) -> list[Company]:
        """Companies matching the coarse filters a Buy Box starts from.

        This is the cheap pass: country, industry and town. Scoring does the rest,
        because a Buy Box's real criteria need facts this query cannot see.
        """
        query = select(Company).where(Company.country.in_([str(c) for c in countries]))
        if industry_keys:
            query = query.where(Company.industry_keys.overlap(list(industry_keys)))
        if city:
            # Partial match on purpose: a Buy Box for "Dallas" should still reach
            # the surrounding towns, which is where most of these businesses are.
            query = query.where(Company.city.ilike(f"%{city}%"))

        result = await self.session.scalars(
            query.options(selectinload(Company.people))
            .order_by(Company.display_name)
            .limit(limit)
            .offset(offset)
        )
        return list(result)

    async def by_ids(self, ids: Sequence[uuid.UUID]) -> dict[uuid.UUID, Company]:
        """Several companies in one query, keyed by id."""
        if not ids:
            return {}
        result = await self.session.scalars(select(Company).where(Company.id.in_(list(ids))))
        return {company.id: company for company in result}

    async def with_relations(self, entity_id: uuid.UUID) -> Company | None:
        """One company with its people loaded.

        Both are eager-loaded because a lazy load inside async code fails at
        runtime rather than at import, which is a nasty way to find out.
        """
        company: Company | None = await self.session.scalar(
            select(Company).where(Company.id == entity_id).options(selectinload(Company.people))
        )
        return company

    async def find_duplicate_candidates(
        self,
        *,
        normalized_name: str,
        domain: str | None,
        phone_e164: str | None,
        latitude: float | None,
        longitude: float | None,
        exclude_id: object | None = None,
    ) -> list[Company]:
        """Rows that might be the same business.

        Cheap filters first (an exact domain or phone match is decisive), then a
        geographic window narrowed by name similarity. This is a candidate list, not
        a decision: the matcher scores each pair.
        """
        conditions = []
        if domain:
            conditions.append(Company.domain == domain)
        if phone_e164:
            conditions.append(Company.phone_e164 == phone_e164)
        if latitude is not None and longitude is not None:
            point = ST_SetSRID(ST_MakePoint(longitude, latitude), WGS84)
            conditions.append(
                ST_DWithin(Company.geo, point, NEARBY_METRES)
                & (
                    func.similarity(Company.normalized_name, normalized_name)
                    > NAME_SIMILARITY_THRESHOLD
                )
            )

        if not conditions:
            return []

        query = select(Company).where(or_(*conditions))
        if exclude_id is not None:
            query = query.where(Company.id != exclude_id)

        # Decisive matches first: in a dense area, many similar names nearby could
        # otherwise push the one company sharing this website past the limit.
        priority = []
        if domain:
            priority.append((Company.domain == domain).desc())
        if phone_e164:
            priority.append((Company.phone_e164 == phone_e164).desc())

        result = await self.session.scalars(
            query.order_by(*priority, Company.display_name).limit(MAX_DUPLICATE_CANDIDATES)
        )
        return list(result)

    async def coordinates(
        self, company_ids: Sequence[uuid.UUID]
    ) -> dict[uuid.UUID, tuple[float, float]]:
        """Latitude and longitude for the companies that have a location.

        Companies without one are simply absent from the result, so a caller can
        say how many it could not place rather than inventing a position.
        """
        if not company_ids:
            return {}
        point = cast(Company.geo, Geometry)
        rows = await self.session.execute(
            select(Company.id, ST_Y(point), ST_X(point)).where(
                Company.id.in_(list(company_ids)), Company.geo.is_not(None)
            )
        )
        return {company_id: (float(lat), float(lng)) for company_id, lat, lng in rows}

    async def needing_field(
        self,
        field: str,
        *,
        task: EnrichmentTask,
        limit: int,
        country: Country | None = None,
        require_domain: bool = False,
    ) -> list[Company]:
        """Companies that have never had `field` recorded, so a job never repeats work."""
        already_recorded = exists().where(
            FieldValue.company_id == Company.id, FieldValue.field == field
        )
        query = select(Company).where(~already_recorded)
        if country is not None:
            query = query.where(Company.country == country)
        if require_domain:
            query = query.where(Company.domain.is_not(None))
        result = await self.session.scalars(least_recently_tried(query, task).limit(limit))
        return list(result)

    async def with_known_headcount(self) -> list[Company]:
        """Companies with a stated headcount or a register band: the ones we can estimate."""
        result = await self.session.scalars(
            select(Company)
            .where(or_(Company.employee_count.is_not(None), Company.employee_band.is_not(None)))
            .order_by(Company.display_name)
        )
        return list(result)

    async def needing_register_lookup(self, country: Country, *, limit: int) -> list[Company]:
        """Companies in a country that have not been matched to a register yet."""
        query = select(Company).where(Company.country == country, Company.legal_name.is_(None))
        result = await self.session.scalars(
            least_recently_tried(query, EnrichmentTask.REGISTRY).limit(limit)
        )
        return list(result)

    async def needing_website_read(self, *, limit: int) -> list[Company]:
        """Companies with a website that nobody has read yet."""
        query = select(Company).where(Company.website_url.is_not(None), Company.summary.is_(None))
        result = await self.session.scalars(
            least_recently_tried(query, EnrichmentTask.WEBSITE).limit(limit)
        )
        return list(result)


def least_recently_tried(
    query: Select[tuple[Company]], task: EnrichmentTask
) -> Select[tuple[Company]]:
    """Companies never tried first, then the ones tried longest ago.

    Some companies can never be done (no published date, no register match). They
    are still retried, but only after everything new, so every run makes progress.
    """
    last_attempt = EnrichmentAttempt.attempted_at
    return query.outerjoin(
        EnrichmentAttempt,
        (EnrichmentAttempt.company_id == Company.id) & (EnrichmentAttempt.task == task),
    ).order_by(last_attempt.asc().nulls_first(), Company.display_name)
