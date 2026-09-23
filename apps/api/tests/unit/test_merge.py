"""How far each source is trusted when two of them disagree."""

from __future__ import annotations

from dealsignal.matching.merge import DEFAULT_CONFIDENCE, confidence_of
from dealsignal.models.enums import SourceName


def test_an_official_register_outranks_the_website_which_outranks_a_map_listing() -> None:
    register = confidence_of(SourceName.COMPANIES_HOUSE)
    website = confidence_of(SourceName.WEBSITE)
    listing = confidence_of(SourceName.OVERTURE)

    assert register > website > listing


def test_our_own_estimates_are_trusted_least() -> None:
    assert confidence_of(SourceName.ESTIMATE) == min(confidence_of(source) for source in SourceName)


def test_an_unlisted_source_gets_the_default() -> None:
    assert confidence_of("somewhere_new") == DEFAULT_CONFIDENCE  # type: ignore[arg-type]
