"""Running one background job from the command line.

The jobs are the only implementation: the Load & enrich tab queues them on the
worker, and these scripts await the same function, so both paths behave identically.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

from dealsignal.core.config import get_settings
from dealsignal.core.errors import DealSignalError
from dealsignal.core.logging import configure_logging
from dealsignal.db.session import dispose_engine, init_engine

Job = Callable[..., Awaitable[dict[str, Any]]]


def describe(report: dict[str, Any]) -> str:
    """What the job did, including what it could not do and why."""
    lines = []
    if note := report.get("note"):
        lines.append(str(note))
    attempted = int(report.get("attempted", 0))
    if attempted:
        lines.append(f"{report.get('succeeded', 0)} of {attempted} succeeded.")
    lines += [
        f"  [skip] {failure['company']}: {failure['reason']}"
        for failure in report.get("failures", [])
    ]
    return "\n".join(lines)


def run(job: Job, **arguments: Any) -> int:
    """Run one job to completion and print its report. Returns an exit code."""
    settings = get_settings()
    configure_logging(settings)

    async def main() -> dict[str, Any]:
        init_engine(settings)
        try:
            return await job({}, **arguments)
        finally:
            await dispose_engine()

    try:
        report = asyncio.run(main())
    except DealSignalError as error:
        print(f"Could not finish: {error.message}")  # noqa: T201
        return 1
    print(describe(report))  # noqa: T201
    return 0
