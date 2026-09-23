"""Field-level provenance storage.

One row per field per source. The company row holds the winning value; these rows
hold every answer we have seen and where it came from, which is what the UI shows
next to a field and what makes a wrong value traceable.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import datetime
from typing import Any

from sqlalchemy import distinct, func, select
from sqlalchemy.dialects.postgresql import insert

from dealsignal.models.enums import SourceName
from dealsignal.models.source import FieldValue
from dealsignal.repositories.base import BaseRepository


class FieldValueRepository(BaseRepository[FieldValue]):
    model = FieldValue

    async def for_company(self, company_id: uuid.UUID, field: str) -> list[FieldValue]:
        result = await self.session.scalars(
            select(FieldValue).where(FieldValue.company_id == company_id, FieldValue.field == field)
        )
        return list(result)

    async def sources_for(self, company_ids: Sequence[uuid.UUID]) -> dict[uuid.UUID, list[str]]:
        """Which sources contributed facts to each company, in one query."""
        if not company_ids:
            return {}
        rows = await self.session.execute(
            select(FieldValue.company_id, func.array_agg(distinct(FieldValue.source)))
            .where(FieldValue.company_id.in_(list(company_ids)))
            .group_by(FieldValue.company_id)
        )
        return {company_id: sorted(sources) for company_id, sources in rows}

    async def all_for_company(self, company_id: uuid.UUID) -> list[FieldValue]:
        """Every answer every source gave about one company, in one query."""
        result = await self.session.scalars(
            select(FieldValue)
            .where(FieldValue.company_id == company_id)
            .order_by(FieldValue.field, FieldValue.confidence.desc())
        )
        return list(result)

    async def record(
        self,
        *,
        company_id: uuid.UUID,
        field: str,
        value: Any,
        source: SourceName,
        observed_at: datetime,
        confidence: float,
        evidence: str | None = None,
    ) -> None:
        """Store what this source says, replacing that source's previous answer.

        Re-running an ingest must not pile up duplicate rows, so this is an upsert
        keyed by (company, field, source).
        """
        statement = insert(FieldValue).values(
            company_id=company_id,
            field=field,
            value=value,
            source=source,
            confidence=confidence,
            evidence=evidence,
            observed_at=observed_at,
        )
        await self.session.execute(
            statement.on_conflict_do_update(
                constraint="uq_field_value_per_source",
                set_={
                    "value": statement.excluded.value,
                    "confidence": statement.excluded.confidence,
                    "evidence": statement.excluded.evidence,
                    "observed_at": statement.excluded.observed_at,
                },
            )
        )
