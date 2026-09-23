"""The pure half of ingest: cleaning a record before it is stored or compared."""

from __future__ import annotations

from dealsignal.models.enums import Country, SourceName
from dealsignal.services.ingest import IngestReport, clean
from dealsignal.sources.base import PlaceRecord


def record(**overrides: object) -> PlaceRecord:
    defaults: dict[str, object] = {
        "source": SourceName.OVERTURE,
        "external_id": "abc123",
        "name": "Baker Brothers Plumbing & Air, LLC",
        "country": Country.US,
        "website": "https://www.bakerbrothersplumbing.com/contact",
        "phone": "(214) 892-2350",
        "latitude": 32.79,
        "longitude": -96.63,
    }
    return PlaceRecord(**{**defaults, **overrides})


def test_cleaning_normalises_the_fields_matching_depends_on() -> None:
    cleaned = clean(record())

    assert cleaned.normalized_name == "baker brothers plumbing air"
    assert cleaned.domain == "bakerbrothersplumbing.com"
    assert cleaned.phone_e164 == "+12148922350"


def test_an_unusable_phone_becomes_none_rather_than_junk() -> None:
    cleaned = clean(record(phone="N/A"))

    assert cleaned.phone_e164 is None


def test_a_missing_website_becomes_none() -> None:
    cleaned = clean(record(website=None))

    assert cleaned.domain is None


def test_the_candidate_carries_coordinates_for_distance_checks() -> None:
    candidate = clean(record()).as_candidate()

    assert candidate.latitude == 32.79
    assert candidate.domain == "bakerbrothersplumbing.com"


def test_the_report_counts_what_was_stored() -> None:
    report = IngestReport(seen=10, created=7, merged=2, needs_review=1)

    assert report.stored == 9
    assert report.seen - report.stored == 1, "one record was seen but not stored"
