"""The reader's manners: robots.txt, blocks, and what it does with what it finds."""

from __future__ import annotations

import httpx
import pytest
import respx

from dealsignal.core.config import Settings
from dealsignal.core.errors import SourceBlockedError
from dealsignal.sources.website import WebsiteReader

SITE = "https://bakerbrothersplumbing.com"
HOME_HTML = """
<html><body>
  <h1>Baker Brothers Plumbing & Air</h1>
  <p>Serving Dallas families since 1996 with drain cleaning and air conditioning
     repair. Ask about our annual maintenance plan for homes and businesses.</p>
  <a href="/about/">About us</a>
  <a href="/blog/2024/tips">Blog</a>
  <a href="https://facebook.com/baker">Facebook</a>
  <footer>&copy; 2019 Baker Brothers</footer>
</body></html>
"""
ABOUT_HTML = """
<html><body><h1>About</h1>
<p>Baker Brothers is a family owned business founded in 1996 by Pat Baker, still
   run by the Baker family from a single location in Dallas, Texas.</p>
</body></html>
"""


@pytest.fixture
def settings() -> Settings:
    return Settings(
        environment="ci",
        crawler_requests_per_domain_per_second=1000,  # no real waiting in tests
        crawler_max_pages_per_site=3,
    )


@respx.mock
async def test_it_reads_the_home_page_and_the_pages_worth_reading(settings: Settings) -> None:
    respx.get(f"{SITE}/robots.txt").mock(return_value=httpx.Response(404))
    respx.get(f"{SITE}/about").mock(return_value=httpx.Response(200, html=ABOUT_HTML))
    respx.get(SITE).mock(return_value=httpx.Response(200, html=HOME_HTML))

    content = await WebsiteReader(settings).read(SITE)

    assert content.has_text
    assert f"{SITE}/about" in content.pages
    assert "family owned" in content.pages[f"{SITE}/about"]
    assert all("facebook" not in page for page in content.pages)


@respx.mock
async def test_a_stale_copyright_year_is_picked_up(settings: Settings) -> None:
    respx.get(f"{SITE}/robots.txt").mock(return_value=httpx.Response(404))
    respx.get(f"{SITE}/about").mock(return_value=httpx.Response(404))
    respx.get(SITE).mock(return_value=httpx.Response(200, html=HOME_HTML))

    content = await WebsiteReader(settings).read(SITE)

    assert content.last_copyright_year == 2019


@respx.mock
async def test_robots_disallow_is_obeyed(settings: Settings) -> None:
    respx.get(f"{SITE}/robots.txt").mock(
        return_value=httpx.Response(200, text="User-agent: *\nDisallow: /")
    )

    with pytest.raises(SourceBlockedError, match=r"robots\.txt"):
        await WebsiteReader(settings).read(SITE)


@respx.mock
async def test_a_403_is_reported_as_blocked_not_as_empty(settings: Settings) -> None:
    respx.get(f"{SITE}/robots.txt").mock(return_value=httpx.Response(404))
    respx.get(SITE).mock(return_value=httpx.Response(403))

    with pytest.raises(SourceBlockedError) as blocked:
        await WebsiteReader(settings).read(SITE)

    assert blocked.value.details["status"] == 403


@respx.mock
async def test_a_missing_subpage_does_not_sink_the_whole_read(settings: Settings) -> None:
    respx.get(f"{SITE}/robots.txt").mock(return_value=httpx.Response(404))
    respx.get(f"{SITE}/about").mock(return_value=httpx.Response(500))
    respx.get(SITE).mock(return_value=httpx.Response(200, html=HOME_HTML))

    content = await WebsiteReader(settings).read(SITE)

    assert SITE in content.pages
    assert f"{SITE}/about" not in content.pages


@respx.mock
async def test_the_home_page_is_fetched_and_sent_once(settings: Settings) -> None:
    """A trailing slash and a link to the https home page each caused another fetch,
    and the same text was sent to the model three times."""
    home_with_self_links = HOME_HTML.replace(
        "</body>",
        f'<a href="{SITE}/">Home</a><a href="http://bakerbrothersplumbing.com">Home</a></body>',
    )
    respx.get(f"{SITE}/robots.txt").mock(return_value=httpx.Response(404))
    respx.get(f"{SITE}/about").mock(return_value=httpx.Response(200, html=ABOUT_HTML))
    home = respx.get(SITE).mock(return_value=httpx.Response(200, html=home_with_self_links))

    content = await WebsiteReader(settings).read(f"{SITE}/")

    assert home.call_count == 1
    assert len(content.pages) == 2, "the home page and the about page, once each"
