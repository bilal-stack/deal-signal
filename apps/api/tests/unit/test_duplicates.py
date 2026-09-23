"""Duplicate detection, using the kind of pairs the real data throws up."""

from __future__ import annotations

import pytest

from dealsignal.matching.duplicates import (
    Candidate,
    compare,
    distance_metres,
    name_similarity,
    names_agree,
)

BAKER = Candidate(
    name="Baker Brothers Plumbing & Air",
    domain="bakerbrothersplumbing.com",
    phone_e164="+12148922350",
    latitude=32.79,
    longitude=-96.63,
)


def test_the_same_website_with_an_agreeing_name_settles_it() -> None:
    other = Candidate(
        name="Baker Bros Plumbing and Air Conditioning",
        domain="bakerbrothersplumbing.com",
    )

    decision = compare(BAKER, other)

    assert decision.merge is True
    assert decision.score == 1.0
    assert "domain" in decision.reason.lower()


def test_one_website_with_different_names_is_for_a_person_to_decide() -> None:
    """A practice lists each dentist: one website, maybe one business, maybe not."""
    first = Candidate(name="Gregory B. Scheideman, DDS", domain="fortworthoralsurgery.com")
    second = Candidate(name="David W. Kostohryz, Jr., DDS, MD", domain="fortworthoralsurgery.com")

    decision = compare(first, second)

    assert (decision.merge, decision.review) == (False, True)
    assert decision.reason == "Same website, but different business names"


def test_one_website_far_apart_is_a_chain_or_franchise_question() -> None:
    fort_worth = Candidate(
        name="Comfort Pros of Fort Worth",
        domain="comfortpros.com",
        latitude=32.75,
        longitude=-97.33,
    )
    sugar_land = Candidate(
        name="Comfort Pros of Sugar Land",
        domain="comfortpros.com",
        latitude=29.62,
        longitude=-95.63,
    )

    decision = compare(fort_worth, sugar_land)

    assert (decision.merge, decision.review) == (False, True)
    assert "km apart" in decision.reason


def test_one_website_with_different_location_pages_is_not_merged() -> None:
    """Franchises point each location at its own page on the brand's website."""
    first = Candidate(name="Comfort Pros", domain="comfortpros.com", website_path="ft-worth")
    second = Candidate(name="Comfort Pros", domain="comfortpros.com", website_path="arlington")

    decision = compare(first, second)

    assert (decision.merge, decision.review) == (False, True)
    assert "location pages" in decision.reason


def test_the_home_page_and_a_page_on_it_can_still_be_one_business() -> None:
    first = Candidate(name="Comfort Pros", domain="comfortpros.com", website_path="")
    second = Candidate(name="Comfort Pros LLC", domain="comfortpros.com", website_path="contact")

    assert compare(first, second).merge is True


@pytest.mark.parametrize(
    ("left", "right"),
    [
        ("Ray's A/C & Heating Services.", "Rays AC and Heating Services"),
        ("Andrew's Air Conditioning", "Andrews Air Conditioning & Refrigeration"),
        ("EZ Blast A/C & Heat", "EZ Blast AC & Heat, LLC"),
        ("Comfort Experts", "Comfort Experts Inc."),
        ("1st Choice Richmond Duct Cleaning", "1stchoicerichmondductcleaning"),
        ("Baker Bros Plumbing and Air Conditioning", "Baker Brothers Plumbing & Air"),
    ],
)
def test_spellings_of_one_name_agree(left: str, right: str) -> None:
    assert names_agree(left, right)


@pytest.mark.parametrize(
    ("left", "right"),
    [
        ("Northside Air Conditioning & Heating, INC.", "Elm Street Plumbing"),
        ("Kristy Hong", "Kreating Smiles Pediatric Dentistry"),
        ("Donalson Brothers Plumbing Co.", "Vogt Air Conditioning"),
        ("F I S", "Flueclean Installations Services Ltd."),
    ],
)
def test_different_businesses_do_not_agree(left: str, right: str) -> None:
    assert not names_agree(left, right)


def test_same_phone_and_name_at_one_address_merges() -> None:
    other = Candidate(
        name="Baker Brothers Plumbing and Air",
        phone_e164="+12148922350",
        latitude=32.7901,
        longitude=-96.6301,
    )

    decision = compare(BAKER, other)

    assert decision.merge is True


def test_a_similar_name_alone_is_only_worth_a_review() -> None:
    other = Candidate(name="Baker Brothers Plumbing")

    decision = compare(BAKER, other)

    assert decision.merge is False


def test_two_different_businesses_do_not_match() -> None:
    other = Candidate(
        name="Craddock Lumber Co",
        domain="craddocklumber.com",
        phone_e164="+12145551234",
        latitude=32.71,
        longitude=-96.80,
    )

    decision = compare(BAKER, other)

    assert decision.merge is False
    assert decision.review is False


def test_distance_is_none_when_coordinates_are_missing() -> None:
    assert distance_metres(BAKER, Candidate(name="Somewhere")) is None


def test_distance_is_metres_between_two_points() -> None:
    near = Candidate(name="x", latitude=32.7901, longitude=-96.6301)

    metres = distance_metres(BAKER, near)

    assert metres is not None
    assert metres < 20


def test_name_similarity_ignores_legal_suffixes_and_word_order() -> None:
    assert name_similarity("Craddock Lumber Co", "Lumber Craddock LLC") > 0.9
    assert name_similarity("Craddock Lumber", "Dallas Door & Supply") < 0.5
