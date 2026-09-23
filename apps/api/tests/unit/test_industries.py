"""Relevance starts here: what a typed industry is allowed to match."""

from __future__ import annotations

import pytest

from dealsignal.sources.industries import INDUSTRIES, resolve, supported_labels


@pytest.mark.parametrize(
    ("typed", "expected_key"),
    [
        ("HVAC", "hvac"),
        ("hvac", "hvac"),
        ("Heating and Air Conditioning", "hvac"),
        ("  air conditioning  ", "hvac"),
        ("Plumbing", "plumbing"),
        ("plumber", "plumbing"),
        ("commercial cleaning companies", "commercial_cleaning"),
        ("dentist", "dental"),
    ],
)
def test_common_phrasings_resolve(typed: str, expected_key: str) -> None:
    industry = resolve(typed)

    assert industry is not None
    assert industry.key == expected_key


@pytest.mark.parametrize(
    "typed",
    ["", "   ", "lumber", "home health", "electronics recycling", "interior plants"],
)
def test_unrelated_terms_do_not_resolve(typed: str) -> None:
    """The failure mode we are fixing: 'HVAC' must never reach a lumber yard."""
    assert resolve(typed) is None


def test_industry_keys_are_unique() -> None:
    keys = [industry.key for industry in INDUSTRIES]

    assert len(keys) == len(set(keys))


def test_no_alias_is_claimed_by_two_industries() -> None:
    seen: dict[str, str] = {}
    for industry in INDUSTRIES:
        for alias in industry.aliases:
            assert alias not in seen, f"{alias!r} claimed by {seen.get(alias)} and {industry.key}"
            seen[alias] = industry.key


def test_every_industry_has_categories_and_a_code() -> None:
    for industry in INDUSTRIES:
        assert industry.categories, f"{industry.key} has no categories to match on"
        assert industry.naics.isdigit()


def test_supported_labels_are_listed_for_error_messages() -> None:
    labels = supported_labels()

    assert "HVAC" in labels
    assert labels == sorted(labels)


VERIFIED_SLUGS: frozenset[str] = frozenset(
    {
        # Counted in a real Overture release over the Dallas-Fort Worth box.
        "hvac_services",
        "air_duct_cleaning_service",
        "plumbing",
        "electrician",
        "landscaping",
        "landscape_architect",
        "accountant",
        "general_dentistry",
        "cosmetic_dentist",
        "pediatric_dentist",
        "veterinarian",
        "office_cleaning",
        "cleaning_services",
        "b2b_cleaning_and_waste_management",
    }
)


def test_every_category_slug_is_one_that_exists_in_the_data() -> None:
    """An invented slug returns nothing, which reads exactly like "no businesses
    here". This test is the record of which slugs were actually verified."""
    for industry in INDUSTRIES:
        unknown = industry.categories - VERIFIED_SLUGS
        assert not unknown, f"{industry.key} uses unverified slugs: {sorted(unknown)}"


def test_household_services_are_not_sold_as_commercial_cleaning() -> None:
    """A buyer asking for commercial cleaning does not want dry cleaners or pool
    services, both of which sit in neighbouring categories."""
    cleaning = next(industry for industry in INDUSTRIES if industry.key == "commercial_cleaning")

    assert "dry_cleaning" not in cleaning.categories
    assert "pool_cleaning" not in cleaning.categories
    assert "home_cleaning" not in cleaning.categories
