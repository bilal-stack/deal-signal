"""Which pages get read, and what the footer tells us."""

from __future__ import annotations

import pytest

from dealsignal.sources.website_pages import choose_pages, copyright_year, page_score, same_site

BASE = "https://bakerbrothersplumbing.com"


def test_the_home_page_always_comes_first() -> None:
    pages = choose_pages(BASE, ["/services/", "/about/"], limit=6)

    assert pages[0] == BASE


def test_about_beats_pricing() -> None:
    pages = choose_pages(BASE, ["/pricing/", "/about-us/"], limit=6)

    assert pages.index(f"{BASE}/about-us") < pages.index(f"{BASE}/pricing")


def test_off_site_links_are_ignored() -> None:
    pages = choose_pages(BASE, ["https://facebook.com/about", "/about/"], limit=6)

    assert all("facebook" not in page for page in pages)


def test_files_and_low_value_sections_are_skipped() -> None:
    links = ["/brochure.pdf", "/blog/2024/why-hvac", "/privacy/", "/cart/", "/about/"]

    pages = choose_pages(BASE, links, limit=6)

    assert pages == [BASE, f"{BASE}/about"]


def test_duplicates_and_anchors_collapse() -> None:
    pages = choose_pages(BASE, ["/about/", "/about", "/about#team"], limit=6)

    assert pages.count(f"{BASE}/about") == 1


def test_the_limit_is_respected() -> None:
    links = ["/about/", "/services/", "/team/", "/contact/", "/careers/", "/history/"]

    assert len(choose_pages(BASE, links, limit=3)) == 3


def test_www_counts_as_the_same_site() -> None:
    assert same_site(BASE, "https://www.bakerbrothersplumbing.com/about") is True
    assert same_site(BASE, "https://competitor.com/about") is False


def test_an_unknown_page_is_not_worth_fetching() -> None:
    assert page_score(f"{BASE}/some/deep/marketing/page") == 0


@pytest.mark.parametrize(
    ("html", "expected"),
    [
        ("<footer>© 2019 Baker Brothers</footer>", 2019),
        ("<p>Copyright 2005 - 2024 Craddock Lumber</p>", 2024),
        ("&copy; 2026 Fresh Co", 2026),
        ("<footer>All rights reserved</footer>", None),
        ("<footer>© 1887 since forever</footer>", None),
    ],
)
def test_copyright_year_reads_the_newest_plausible_year(html: str, expected: int | None) -> None:
    assert copyright_year(html, current_year=2026) == expected


def test_a_future_copyright_year_is_not_believed() -> None:
    assert copyright_year("© 2099 Time Travellers Ltd", current_year=2026) is None


def test_one_page_under_several_spellings_is_chosen_once() -> None:
    """http, https, www and a trailing slash all reach the same page."""
    chosen = choose_pages(
        "http://www.example.com/",
        ["https://www.example.com/", "https://example.com", "/about/", "https://example.com/about"],
        limit=5,
    )

    assert chosen == ["http://www.example.com", "http://www.example.com/about"]
