"""Merging two company records into one.

Everything attached to the loser moves to the winner: its sources, its recorded
field values, its people. Fields the winner does not have are filled from the
loser, and fields it already has are kept, because the winner is the record the
matcher was more confident about.

Nothing is thrown away silently. If a merge cannot be completed, it raises and the
caller reports it.
"""

from __future__ import annotations

import uuid

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from dealsignal.core.errors import ConflictError, NotFoundError
from dealsignal.core.logging import get_logger
from dealsignal.models.company import Company
from dealsignal.models.person import Person
from dealsignal.models.source import FieldValue
from dealsignal.repositories.company import CompanyRepository

log = get_logger(__name__)

FILLABLE_FIELDS: tuple[str, ...] = (
    "legal_name",
    "domain",
    "website_url",
    "phone_e164",
    "street",
    "city",
    "region",
    "postal_code",
    "geo",
    "industry_label",
    "industry_code",
    "founded_year",
    "employee_band",
    "employee_count",
    "revenue_low",
    "revenue_high",
    "summary",
)
"""Columns the surviving record may take from the one being absorbed."""


class CompanyMerger:
    """Folds one company record into another."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._companies = CompanyRepository(session)

    async def merge(self, keep_id: uuid.UUID, absorb_id: uuid.UUID) -> Company:
        """Move everything from `absorb_id` onto `keep_id` and delete the loser."""
        if keep_id == absorb_id:
            raise ConflictError("A company cannot be merged into itself.")

        keep = await self._companies.get(keep_id)
        absorb = await self._companies.get(absorb_id)
        if keep is None or absorb is None:
            missing = keep_id if keep is None else absorb_id
            raise NotFoundError(f"No company with id {missing}.")

        # Order matters. Unique columns such as the domain cannot exist on both
        # records at once, so the values are captured, the absorbed record is
        # deleted, and only then does the survivor take them.
        gaps = self.gap_values(keep, absorb)
        await self._move_children(keep_id, absorb_id)
        await self._session.delete(absorb)
        await self._session.flush()

        for field, value in gaps.items():
            setattr(keep, field, value)
        await self._session.flush()

        log.info("companies_merged", kept=str(keep_id), absorbed=str(absorb_id))
        return keep

    @staticmethod
    def gap_values(keep: Company, absorb: Company) -> dict[str, object]:
        """What the survivor is missing that the absorbed record knows.

        Values the survivor already has are never overwritten: it is the record
        the matcher trusted.
        """
        return {
            field: getattr(absorb, field)
            for field in FILLABLE_FIELDS
            if getattr(keep, field, None) is None and getattr(absorb, field, None) is not None
        }

    async def _move_children(self, keep_id: uuid.UUID, absorb_id: uuid.UUID) -> None:
        """Re-point recorded values and people at the surviving company.

        Both records may hold the same field from the same source, or the same
        person. Moving those would break the unique constraints, so the loser's
        copy is dropped first: the surviving record is the one the matcher trusted.
        """
        await self._drop_colliding(FieldValue, keep_id, absorb_id, ("field", "source"))
        await self._drop_colliding(Person, keep_id, absorb_id, ("full_name",))

        for model in (FieldValue, Person):
            await self._session.execute(
                update(model).where(model.company_id == absorb_id).values(company_id=keep_id)
            )

    async def _drop_colliding(
        self,
        model: type[FieldValue] | type[Person],
        keep_id: uuid.UUID,
        absorb_id: uuid.UUID,
        key_fields: tuple[str, ...],
    ) -> None:
        """Remove the loser's rows that the winner already has an equivalent of."""
        columns = [getattr(model, field) for field in key_fields]
        kept_keys = {
            tuple(row)
            for row in await self._session.execute(
                select(*columns).where(model.company_id == keep_id)
            )
        }
        if not kept_keys:
            return

        rows = await self._session.execute(
            select(model.id, *columns).where(model.company_id == absorb_id)
        )
        colliding = [row[0] for row in rows if tuple(row[1:]) in kept_keys]
        if colliding:
            await self._session.execute(delete(model).where(model.id.in_(colliding)))
