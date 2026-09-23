"""Merging: what the surviving record keeps, takes, and never loses."""

from __future__ import annotations

from dealsignal.models.company import Company
from dealsignal.models.enums import Country
from dealsignal.services.merge_companies import FILLABLE_FIELDS, CompanyMerger


def company(**overrides: object) -> Company:
    defaults: dict[str, object] = {
        "display_name": "Baker Brothers",
        "normalized_name": "baker brothers",
        "country": Country.US,
    }
    return Company(**{**defaults, **overrides})


def test_gaps_are_filled_from_the_absorbed_record() -> None:
    keep = company(domain="baker.com", phone_e164=None, founded_year=None)
    absorb = company(domain=None, phone_e164="+12145550000", founded_year=1996)

    gaps = CompanyMerger.gap_values(keep, absorb)

    assert gaps["phone_e164"] == "+12145550000"
    assert gaps["founded_year"] == 1996


def test_what_the_survivor_already_knows_is_kept() -> None:
    """The surviving record is the one the matcher trusted; it does not get overwritten."""
    keep = company(domain="baker.com", city="Dallas")
    absorb = company(domain="other.com", city="Fort Worth")

    gaps = CompanyMerger.gap_values(keep, absorb)

    assert "domain" not in gaps
    assert "city" not in gaps


def test_the_fillable_list_does_not_include_identity_fields() -> None:
    """Merging must never rewrite who the surviving record is."""
    for field in ("id", "display_name", "normalized_name", "country", "created_at"):
        assert field not in FILLABLE_FIELDS
