from __future__ import annotations

import pytest

from dealsignal.matching.normalize import (
    normalize_domain,
    normalize_name,
    normalize_phone,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Craddock Lumber Co", "craddock lumber"),
        ("Dallas Door & Supply Co.", "dallas door supply"),
        ("Ornata Residential Services, LLC", "ornata residential services"),
        ("THE Clean Air Gardening Company", "clean air gardening"),
        ("Café Métro SARL", "cafe metro"),
    ],
)
def test_normalize_name_keeps_only_the_identifying_words(raw: str, expected: str) -> None:
    assert normalize_name(raw) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("https://WWW.Dallasdoor.com/contact?x=1", "dallasdoor.com"),
        ("http://craddocklumber.com/", "craddocklumber.com"),
        ("stselectronicrecyclinginc.com", "stselectronicrecyclinginc.com"),
        ("sub.example.co.uk", "example.co.uk"),
    ],
)
def test_normalize_domain_reduces_to_the_registrable_domain(raw: str, expected: str) -> None:
    assert normalize_domain(raw) == expected


@pytest.mark.parametrize("raw", [None, "", "not a domain", "http://"])
def test_normalize_domain_returns_none_when_there_is_nothing_usable(raw: str | None) -> None:
    assert normalize_domain(raw) is None


def test_normalize_phone_formats_a_valid_number() -> None:
    assert normalize_phone("(214) 741-2411", country="US") == "+12147412411"


def test_normalize_phone_accepts_an_already_international_number() -> None:
    assert normalize_phone("+44 20 7946 0958", country="GB") == "+442079460958"


@pytest.mark.parametrize("raw", [None, "", "N/A", "123"])
def test_normalize_phone_returns_none_rather_than_a_wrong_number(raw: str | None) -> None:
    assert normalize_phone(raw, country="US") is None
