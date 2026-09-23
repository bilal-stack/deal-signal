"""Recompute every stored revenue estimate.

    python -m dealsignal.scripts.estimates

Run it after the benchmark file changes (scripts/fetch_benchmarks.py), so stored
estimates match the figures the method now cites. Only companies with a known
headcount get an estimate; the rest stay unknown.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from dealsignal.core.config import get_settings
from dealsignal.core.logging import configure_logging
from dealsignal.db.session import dispose_engine, init_engine, session_scope
from dealsignal.repositories.company import CompanyRepository
from dealsignal.repositories.field_value import FieldValueRepository
from dealsignal.services.estimates import record_revenue_estimate


async def recompute() -> int:
    """Returns how many companies were re-estimated."""
    settings = get_settings()
    configure_logging(settings)
    init_engine(settings)
    try:
        async with session_scope() as session:
            companies = await CompanyRepository(session).with_known_headcount()
            fields = FieldValueRepository(session)
            observed_at = datetime.now(UTC)
            for company in companies:
                await record_revenue_estimate(company, fields, observed_at=observed_at)
    finally:
        await dispose_engine()
    return len(companies)


def main() -> int:
    updated = asyncio.run(recompute())
    print(f"Recomputed revenue estimates for {updated} companies.")  # noqa: T201
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
