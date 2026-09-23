"""Read one company's website with Claude, and keep the answer for tests.

    python -m dealsignal.scripts.record_website_read --company <id>

Exactly one Claude call, never retried. The company is enriched the same way the
background job does it, and the reply is saved to tests/fixtures/claude/
website_read.json. The website's text is not saved: only the page addresses and
sizes, plus Claude's reply, which quotes one sentence per fact.
"""

from __future__ import annotations

import argparse
import asyncio
import re
import sys
import uuid
from typing import Any

from dealsignal.ai.extractor import WebsiteExtractor
from dealsignal.core.config import get_settings
from dealsignal.core.logging import configure_logging
from dealsignal.db.session import dispose_engine, init_engine, session_scope
from dealsignal.models.enums import EnrichmentTask
from dealsignal.repositories.company import CompanyRepository
from dealsignal.repositories.enrichment_attempt import EnrichmentAttemptRepository
from dealsignal.scripts.claude_recording import (
    ExchangeRecorder,
    recording_client,
    request_summary,
    save_fixture,
)
from dealsignal.services.enrichment import WebsiteEnrichmentService
from dealsignal.sources.website import WebsiteReader

PAGE_MARKER = re.compile(r"----- PAGE: (\S+) -----\n")


def page_sizes(request: dict[str, Any]) -> dict[str, int]:
    """Each page sent and its length, without the page text itself."""
    sections = PAGE_MARKER.split(request["messages"][0]["content"])[1:]
    return {sections[i]: len(sections[i + 1]) for i in range(0, len(sections), 2)}


async def record(company_id: uuid.UUID) -> int:
    settings = get_settings()
    configure_logging(settings)
    recorder = ExchangeRecorder()
    client = recording_client(settings, recorder)

    init_engine(settings)
    try:
        async with session_scope() as session:
            company = await CompanyRepository(session).get(company_id)
            if company is None or not company.website_url:
                print(f"No company {company_id} with a website.", file=sys.stderr)  # noqa: T201
                return 1

            service = WebsiteEnrichmentService(
                session, WebsiteReader(settings), WebsiteExtractor(settings, client=client)
            )
            outcome = await service.enrich(company)
            await EnrichmentAttemptRepository(session).record(
                company.id,
                EnrichmentTask.WEBSITE,
                succeeded=outcome.succeeded,
                message=outcome.message,
            )
            name, url = company.display_name, company.website_url
    finally:
        await client.close()
        await dispose_engine()

    learned = ", ".join(outcome.learned_fields) or "nothing"
    print(f"{name}: {outcome.message} Learned: {learned}.")  # noqa: T201
    exchange = recorder.only_success()
    if exchange is None:
        return 0 if outcome.succeeded else 1
    request, response = exchange
    save_fixture(
        "website_read",
        script="record_website_read.py",
        response=response,
        company=name,
        url=url,
        request={**request_summary(request), "page_chars": page_sizes(request)},
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Record one real website read for tests.")
    parser.add_argument("--company", type=uuid.UUID, required=True)
    args = parser.parse_args(argv)
    return asyncio.run(record(args.company))


if __name__ == "__main__":
    raise SystemExit(main())
