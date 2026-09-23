"""Choosing which pages of a company website to read.

A small business site says almost everything useful on a handful of pages. Reading
six well-chosen ones costs a second and a few thousand tokens; crawling the whole
site costs minutes and buys nothing. Everything here is pure, so the choice can be
tested without fetching anything.
"""

from __future__ import annotations

import re
from urllib.parse import urljoin, urlparse

PAGE_PRIORITIES: tuple[tuple[str, int], ...] = (
    ("about", 100),
    ("our-story", 95),
    ("who-we-are", 95),
    ("history", 90),
    ("team", 85),
    ("leadership", 85),
    ("services", 80),
    ("what-we-do", 78),
    ("commercial", 70),
    ("maintenance", 70),
    ("plans", 68),
    ("pricing", 65),
    ("contact", 60),
    ("careers", 40),
)
"""Path fragments worth reading, best first. An About page beats a pricing page
because ownership and founding year are what scoring needs."""

SKIP_PATTERNS = re.compile(
    r"\.(pdf|jpg|jpeg|png|gif|svg|webp|zip|mp4|mov|css|js)$|/(blog|news|privacy|terms|cart|login|account)/",
    re.IGNORECASE,
)

COPYRIGHT_YEAR = re.compile(
    r"(?:\u00a9|&copy;|copyright)\s*(?:\d{4}\s*[-\u2013]\s*)?(\d{4})",
    re.IGNORECASE,
)
MIN_PLAUSIBLE_YEAR = 1990


def page_key(url: str) -> str:
    """One key per page, however the link spells it.

    http and https, a leading www and a trailing slash all reach the same page. As
    distinct keys, a site's home page was fetched three times and sent three times.
    """
    parsed = urlparse(url)
    host = parsed.netloc.lower().removeprefix("www.")
    path = parsed.path.rstrip("/") or "/"
    return f"{host}{path}?{parsed.query}" if parsed.query else f"{host}{path}"


def same_site(base_url: str, url: str) -> bool:
    """True when a link stays on the company's own domain."""
    base_host = urlparse(base_url).netloc.lower().removeprefix("www.")
    host = urlparse(url).netloc.lower().removeprefix("www.")
    return not host or host == base_host


def page_score(url: str) -> int:
    """How much this page is worth reading. 0 means skip it."""
    path = urlparse(url).path.lower()
    if SKIP_PATTERNS.search(url):
        return 0
    if path in ("", "/"):
        return 110
    for fragment, score in PAGE_PRIORITIES:
        if fragment in path:
            return score
    return 0


def choose_pages(base_url: str, links: list[str], *, limit: int) -> list[str]:
    """The pages to fetch, in order, starting with the home page.

    Duplicates, off-site links, files and low-value sections are dropped before
    the limit is applied, so the budget is spent on pages that carry facts.
    """
    seen: set[str] = set()
    scored: list[tuple[int, str]] = []

    for link in [base_url, *links]:
        absolute = urljoin(base_url, link).split("#")[0].rstrip("/") or base_url
        key = page_key(absolute)
        if key in seen or not same_site(base_url, absolute):
            continue
        score = page_score(absolute)
        if score == 0:
            continue
        seen.add(key)
        scored.append((score, absolute))

    scored.sort(key=lambda item: (-item[0], item[1]))
    return [url for _, url in scored[:limit]]


def copyright_year(html: str, *, current_year: int) -> int | None:
    """The newest copyright year on the page, if it looks like a real one.

    A stale copyright is a genuine signal that a site has been left alone, so this
    reads the largest plausible year rather than the first match.
    """
    years = [
        int(match)
        for match in COPYRIGHT_YEAR.findall(html)
        if MIN_PLAUSIBLE_YEAR <= int(match) <= current_year
    ]
    return max(years) if years else None
