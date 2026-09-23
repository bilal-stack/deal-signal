"""Running one enrichment over many companies, and reporting honestly.

Every enrichment service returns an outcome with `succeeded` and `message`, so a
single runner drives them all. The report keeps the failures and their reasons,
because "enriched 12 companies" hides the 38 it could not.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Sequence
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

from dealsignal.models.company import Company

MAX_REPORTED_FAILURES = 25


class Outcome(Protocol):
    @property
    def succeeded(self) -> bool: ...

    @property
    def message(self) -> str: ...


class Failure(BaseModel):
    model_config = ConfigDict(frozen=True)

    company: str
    reason: str


class JobReport(BaseModel):
    """What a background job did. Stored as the job's result and shown in the UI."""

    model_config = ConfigDict(frozen=True)

    job: str
    attempted: int = 0
    succeeded: int = 0
    failures: list[Failure] = Field(default_factory=list)
    note: str | None = None
    """A plain sentence for anything that is not per company, such as a missing key."""

    @property
    def failed(self) -> int:
        return self.attempted - self.succeeded


async def run_batch(
    job: str,
    companies: Sequence[Company],
    enrich: Callable[[Company], Awaitable[Outcome]],
    *,
    record: Callable[[Company, Outcome], Awaitable[None]] | None = None,
    after_each: Callable[[], Awaitable[None]] | None = None,
    pause_seconds: float = 0.0,
) -> JobReport:
    """Enrich each company in turn, pausing between calls to stay polite.

    `record` remembers each outcome, so the next run starts with companies not yet
    tried. `after_each` is where a job commits. Each company's result is then saved
    as soon as it is known: a failure at company 180 no longer throws away the first
    179, and progress is visible while the job runs.
    """
    succeeded = 0
    failures: list[Failure] = []

    for index, company in enumerate(companies):
        outcome = await enrich(company)
        if record is not None:
            await record(company, outcome)
        if after_each is not None:
            await after_each()
        if outcome.succeeded:
            succeeded += 1
        elif len(failures) < MAX_REPORTED_FAILURES:
            failures.append(Failure(company=company.display_name, reason=outcome.message))
        if pause_seconds and index < len(companies) - 1:
            await asyncio.sleep(pause_seconds)

    return JobReport(job=job, attempted=len(companies), succeeded=succeeded, failures=failures)
