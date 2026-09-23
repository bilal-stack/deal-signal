"""Shared hosts identify nobody, so they must never merge two businesses."""

from __future__ import annotations

import pytest

from dealsignal.matching.normalize import normalize_domain
from dealsignal.matching.shared_domains import SHARED_DOMAINS, identity_domain


@pytest.mark.parametrize(
    "url",
    [
        "https://northside-air.business.site/",
        "https://sites.google.com/view/247waterheatersservicesugarlan/home",
        "http://www.wix.com/lphtml/parking?redirectedFor=goodearthhvacservices.com%2F",
        "https://www.linkedin.com/company/addco-plumbing",
        "http://dealer.frigidaire.net/turnerservices-burleson-tx2",
        "https://turbotax.intuit.com/lp/ppc/2596/",
        "https://www.aireserv.com/ft-worth/?cid=LSTL_ASV-US000207",
        "https://m.facebook.com/somebusiness",
    ],
)
def test_a_page_on_a_shared_host_has_no_identity_domain(url: str) -> None:
    assert identity_domain(url) is None


def test_a_business_own_website_keeps_its_domain() -> None:
    assert identity_domain("http://checkmyac.com/about-us") == "checkmyac.com"


def test_no_website_means_no_domain() -> None:
    assert identity_domain(None) is None


def test_every_entry_is_a_registrable_domain() -> None:
    """An entry like "sites.google.com" would never match: URLs reduce to google.com."""
    assert all(normalize_domain(f"https://{domain}/") == domain for domain in SHARED_DOMAINS)
