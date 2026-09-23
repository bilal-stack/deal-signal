"""Mapping Overture rows, including the messy ones."""

from __future__ import annotations

from typing import Any

from dealsignal.models.enums import Country, SourceName
from dealsignal.sources.overture_parsing import to_place_record


def row(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "id": "08f2664ec2b2e0c0",
        "names": {"primary": "Baker Brothers Plumbing & Air"},
        "categories": {"primary": "hvac_services"},
        "addresses": [
            {
                "freeform": "2615 Big Town Blvd",
                "locality": "Mesquite",
                "region": "TX",
                "postcode": "75150",
            }
        ],
        "websites": ["https://bakerbrothersplumbing.com"],
        "phones": ["+1 214-892-2350"],
        "latitude": 32.79,
        "longitude": -96.63,
        "confidence": 0.91,
    }
    return {**base, **overrides}


def test_a_complete_row_maps_across() -> None:
    record = to_place_record(row(), country=Country.US)

    assert record is not None
    assert record.source is SourceName.OVERTURE
    assert record.name == "Baker Brothers Plumbing & Air"
    assert record.category == "hvac_services"
    assert record.city == "Mesquite"
    assert record.postal_code == "75150"
    assert record.website == "https://bakerbrothersplumbing.com"
    assert record.phone == "+1 214-892-2350"


def test_a_row_without_a_name_is_dropped() -> None:
    assert to_place_record(row(names={"primary": "  "}), country=Country.US) is None


def test_a_row_without_an_id_is_dropped() -> None:
    assert to_place_record(row(id=None), country=Country.US) is None


def test_a_low_confidence_row_is_dropped() -> None:
    assert to_place_record(row(confidence=0.2), country=Country.US) is None


def test_missing_optional_fields_stay_none() -> None:
    record = to_place_record(
        row(addresses=None, websites=None, phones=None, categories=None), country=Country.US
    )

    assert record is not None
    assert record.street is None
    assert record.city is None
    assert record.website is None
    assert record.phone is None
    assert record.category is None


def test_empty_strings_are_treated_as_missing() -> None:
    record = to_place_record(row(websites=[""], phones=[]), country=Country.US)

    assert record is not None
    assert record.website is None
    assert record.phone is None
