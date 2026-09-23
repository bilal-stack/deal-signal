"""Enrichment says what went wrong rather than returning an empty success.

These cover the paths that end before any database write.
"""

from __future__ import annotations

from typing import Any

import pytest

from dealsignal.core.errors import ExternalServiceError, SourceBlockedError
from dealsignal.models.company import Company
from dealsignal.models.enums import Country, SourceName
from dealsignal.services.enrichment import WebsiteEnrichmentService
from dealsignal.sources.website import WebsiteContent


def company(website: str | None = "https://example.com") -> Company:
    return Company(
        display_name="Baker Brothers",
        normalized_name="baker brothers",
        country=Country.US,
        website_url=website,
    )


class StubReader:
    def __init__(self, result: Any = None, error: Exception | None = None) -> None:
        self._result = result
        self._error = error

    async def read(self, url: str) -> Any:
        if self._error:
            raise self._error
        return self._result


class StubExtractor:
    def __init__(self, error: Exception | None = None) -> None:
        self._error = error
        self.called = False

    async def extract(self, **_: Any) -> Any:
        self.called = True
        if self._error:
            raise self._error
        raise AssertionError("not expected in these tests")


def service(reader: Any, extractor: Any) -> WebsiteEnrichmentService:
    return WebsiteEnrichmentService(session=None, reader=reader, extractor=extractor)  # type: ignore[arg-type]


async def test_a_company_with_no_website_is_told_so() -> None:
    outcome = await service(StubReader(), StubExtractor()).enrich(company(website=None))

    assert outcome.succeeded is False
    assert "no website" in outcome.message
    assert outcome.facts is None


async def test_a_blocked_site_reports_the_block() -> None:
    blocked = SourceBlockedError(
        "This site blocked our request, so we left it alone.", source=SourceName.WEBSITE
    )

    outcome = await service(StubReader(error=blocked), StubExtractor()).enrich(company())

    assert outcome.succeeded is False
    assert "blocked" in outcome.message


async def test_an_unreachable_site_reports_the_failure() -> None:
    unreachable = ExternalServiceError("Could not reach the site.", source=SourceName.WEBSITE)

    outcome = await service(StubReader(error=unreachable), StubExtractor()).enrich(company())

    assert outcome.succeeded is False
    assert "Could not reach" in outcome.message


async def test_a_site_with_no_readable_text_does_not_reach_the_model() -> None:
    empty = WebsiteContent(
        url="https://example.com",
        pages={"https://example.com": "hi"},
    )
    extractor = StubExtractor()

    outcome = await service(StubReader(result=empty), extractor).enrich(company())

    assert outcome.succeeded is False
    assert "no readable text" in outcome.message
    assert extractor.called is False, "no point paying for a model call on an empty page"


async def test_a_model_failure_is_reported_not_swallowed() -> None:
    content = WebsiteContent(
        url="https://example.com",
        pages={"https://example.com": "x" * 500},
    )
    extractor = StubExtractor(
        error=ExternalServiceError(
            "The website reader could not finish.", source=SourceName.WEBSITE
        )
    )

    outcome = await service(StubReader(result=content), extractor).enrich(company())

    assert outcome.succeeded is False
    assert "could not finish" in outcome.message
    assert outcome.learned_fields == []


@pytest.mark.parametrize("message_fragment", ["no website", "blocked", "no readable text"])
def test_failure_messages_are_written_for_people(message_fragment: str) -> None:
    assert message_fragment.islower()
