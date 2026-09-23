"""Fetching a company website, politely.

What "politely" means here: robots.txt is honoured, one request per domain per
second, a user agent that says who we are and how to reach us, and a hard cap on
pages. When a site refuses us, that is recorded as a blocked source and the other
sources carry on. We never work around a block.
"""

from __future__ import annotations

from datetime import UTC, datetime

import httpx
import trafilatura
from protego import Protego
from pydantic import BaseModel, ConfigDict
from selectolax.parser import HTMLParser

from dealsignal.core.cache import Cache, LocalCache
from dealsignal.core.config import Settings
from dealsignal.core.errors import ExternalServiceError, SourceBlockedError
from dealsignal.core.logging import get_logger
from dealsignal.models.enums import SourceName
from dealsignal.sources.website_pages import choose_pages, copyright_year, page_key

log = get_logger(__name__)

BLOCKED_STATUSES = frozenset({401, 403, 429})
MIN_USEFUL_TEXT_CHARS = 120
"""Total characters across all pages. Below this there is nothing worth sending
to the model, and a small single-page site can still clear it."""


class WebsiteContent(BaseModel):
    """What one website told us."""

    model_config = ConfigDict(frozen=True)

    url: str
    pages: dict[str, str]
    last_copyright_year: int | None = None

    @property
    def total_characters(self) -> int:
        return sum(len(text) for text in self.pages.values())

    @property
    def has_text(self) -> bool:
        return self.total_characters >= MIN_USEFUL_TEXT_CHARS


class WebsiteReader:
    """Reads a handful of pages from one company website."""

    def __init__(
        self,
        settings: Settings,
        client: httpx.AsyncClient | None = None,
        cache: Cache | None = None,
    ) -> None:
        self._settings = settings
        self._client = client
        self._cache = cache or LocalCache()
        self._interval = 1.0 / max(settings.crawler_requests_per_domain_per_second, 0.1)

    async def read(self, url: str) -> WebsiteContent:
        """Fetch and extract the useful pages of a site."""
        client = self._client or httpx.AsyncClient(
            timeout=self._settings.crawler_timeout_seconds,
            follow_redirects=True,
            headers={"User-Agent": self._settings.crawler_user_agent},
        )
        close_client = self._client is None
        try:
            robots = await self._robots(client, url)
            if robots is not None and not robots.can_fetch(url, self._settings.crawler_user_agent):
                raise SourceBlockedError(
                    "This site's robots.txt asks us not to read it, so we skipped it.",
                    source=SourceName.WEBSITE,
                    retryable=False,
                    details={"url": url},
                )

            home_html = await self._fetch(client, url)
            links = self._links(home_html)
            pages_to_read = choose_pages(
                url, links, limit=self._settings.crawler_max_pages_per_site
            )

            pages: dict[str, str] = {}
            host = httpx.URL(url).host
            home = page_key(url)
            for page_url in pages_to_read:
                is_home = page_key(page_url) == home
                if not is_home:
                    # Every process shares this pace, so a site sees one request per
                    # interval no matter how many workers are running.
                    await self._cache.wait_for_turn(host, self._interval)
                html = home_html if is_home else await self._fetch(client, page_url)
                if html is None:
                    continue
                text = (trafilatura.extract(html, include_comments=False) or "").strip()
                # Two addresses can serve one page (/index.html, a redirect). Its text
                # is only worth sending, and paying for, once.
                if text and text not in pages.values():
                    pages[page_url] = text

            return WebsiteContent(
                url=url,
                pages=pages,
                last_copyright_year=copyright_year(
                    home_html or "", current_year=datetime.now(UTC).year
                ),
            )
        finally:
            if close_client:
                await client.aclose()

    async def _robots(self, client: httpx.AsyncClient, url: str) -> Protego | None:
        """The site's rules, or None when it publishes none."""
        robots_url = httpx.URL(url).copy_with(path="/robots.txt", query=None, fragment=None)
        try:
            response = await client.get(str(robots_url))
        except httpx.HTTPError:
            return None
        if response.status_code >= 400:
            return None
        return Protego.parse(response.text)

    async def _fetch(self, client: httpx.AsyncClient, url: str) -> str | None:
        """One page. Blocks raise; ordinary misses return None."""
        try:
            response = await client.get(url)
        except httpx.HTTPError as exc:
            raise ExternalServiceError(
                f"Could not reach {url}.", source=SourceName.WEBSITE
            ) from exc

        if response.status_code in BLOCKED_STATUSES:
            raise SourceBlockedError(
                "This site blocked our request, so we left it alone and used other sources.",
                source=SourceName.WEBSITE,
                details={"url": url, "status": response.status_code},
            )
        if response.status_code >= 400:
            log.info("page_missing", url=url, status=response.status_code)
            return None
        return response.text

    @staticmethod
    def _links(html: str | None) -> list[str]:
        """Every in-page link, for the page chooser to rank."""
        if not html:
            return []
        tree = HTMLParser(html)
        return [
            href
            for node in tree.css("a[href]")
            if (href := node.attributes.get("href")) is not None
        ]
