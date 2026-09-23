"""Reading a website with Claude.

The pages go in; `WebsiteFacts` comes out, validated, with a quote for every fact.
A refusal, a cut-off reply or a transport error becomes an `ExternalServiceError`
rather than a half-filled record: see `ai/structured.py`.
"""

from __future__ import annotations

from typing import Literal

from anthropic import AsyncAnthropic, transform_schema

from dealsignal.ai.prompts import SYSTEM_PROMPT, build_user_message
from dealsignal.ai.schemas import WebsiteFacts
from dealsignal.ai.structured import StructuredCall, claude_client
from dealsignal.core.config import Settings
from dealsignal.core.errors import ExternalServiceError
from dealsignal.core.logging import get_logger
from dealsignal.models.enums import SourceName

log = get_logger(__name__)

MODEL = "claude-opus-5"
EXTRACTION_EFFORT: Literal["low"] = "low"
"""Extraction is a reading task, not a reasoning one: low effort is both enough
and considerably cheaper."""

MAX_TOKENS = 4096
MAX_PAGE_CHARS = 12_000
"""Per page. Small-business pages are short; anything longer is boilerplate."""


class WebsiteExtractor:
    """Turns page text into validated facts."""

    def __init__(self, settings: Settings, client: AsyncAnthropic | None = None) -> None:
        self._call = StructuredCall(
            claude_client(settings, client, needed_for="websites cannot be read"),
            WebsiteFacts,
            model=MODEL,
            effort=EXTRACTION_EFFORT,
            max_tokens=MAX_TOKENS,
            task="The website reader",
        )

    async def extract(self, *, company_name: str, url: str, pages: dict[str, str]) -> WebsiteFacts:
        """Read the pages, or raise with a message a user can act on."""
        trimmed = self._trim(pages)
        if not trimmed:
            raise ExternalServiceError(
                "There were no readable pages on this website.",
                source=SourceName.WEBSITE,
                retryable=False,
            )

        facts = await self._call.ask(
            system=SYSTEM_PROMPT,
            user=build_user_message(company_name=company_name, url=url, pages=trimmed),
            details={"url": url},
        )
        log.info("website_extracted", url=url, known=sorted(facts.known_fields()))
        return facts

    @staticmethod
    def _trim(pages: dict[str, str]) -> dict[str, str]:
        """Cap each page so one long page cannot crowd out the others."""
        return {url: text[:MAX_PAGE_CHARS] for url, text in pages.items() if text.strip()}


RESPONSE_SCHEMA = transform_schema(WebsiteFacts)
"""What every website read sends as its response format. Recorded replies store its
fingerprint, so a test notices when a recording no longer matches the request."""
