"""Turning a stored company into the facts the scorer reads.

This is the only place that knows both the ORM and the scoring context, which keeps
`scoring/` free of database concerns and easy to test.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence

from dealsignal.models.company import Company
from dealsignal.models.enums import EmployeeBand
from dealsignal.models.person import Person
from dealsignal.models.source import FieldValue
from dealsignal.scoring.context import CompanyFacts

OWNER_BIRTH_YEAR = "owner_birth_year"
"""People only come from company registers, so that is where a birth year is from."""

EMPLOYEE_BAND_MIDPOINTS: dict[EmployeeBand, int] = {
    EmployeeBand.B_1_9: 5,
    EmployeeBand.B_10_19: 15,
    EmployeeBand.B_20_49: 35,
    EmployeeBand.B_50_99: 75,
    EmployeeBand.B_100_249: 175,
    EmployeeBand.B_250_PLUS: 300,
}
"""Registries publish bands, not counts. The midpoint is an estimate, and the UI
labels it as one."""


def best_by_field(values: Iterable[FieldValue]) -> dict[str, FieldValue]:
    """The answer we trust most for each field: highest confidence, then newest.

    Sources disagree. Every answer is kept for the provenance view; this is the one
    rule for which of them scoring and the company panel actually use.
    """
    best: dict[str, FieldValue] = {}
    for value in values:
        current = best.get(value.field)
        if current is None or (value.confidence, value.observed_at) > (
            current.confidence,
            current.observed_at,
        ):
            best[value.field] = value
    return best


def employee_estimate(company: Company) -> int | None:
    """An exact count if we have one, otherwise the midpoint of its band."""
    if company.employee_count is not None:
        return company.employee_count
    if company.employee_band is not None:
        return EMPLOYEE_BAND_MIDPOINTS.get(EmployeeBand(company.employee_band))
    return None


def headcount_basis(company: Company) -> str | None:
    """Where the headcount behind an estimate came from, when it is not a stated count."""
    if company.employee_count is None and company.employee_band is not None:
        return f"midpoint of the register's {company.employee_band} band"
    return None


def primary_owner(people: Sequence[Person]) -> Person | None:
    """The owner worth contacting: a real person, preferring a known birth year.

    Registers list holding companies as directors. They cannot retire and cannot
    take a call, so they never become the named owner; a corporate director is
    recorded separately as a sign the business has a parent.
    """
    people_owners = [person for person in people if person.is_owner and not person.is_company]
    if not people_owners:
        return None
    return max(
        people_owners,
        key=lambda person: (person.birth_year is not None, person.birth_year or 0),
    )


def corporate_directors(people: Sequence[Person]) -> list[Person]:
    """Holding companies listed as directors, which suggest a parent company."""
    return [person for person in people if person.is_company]


def build_company_facts(
    company: Company,
    *,
    people: Sequence[Person] | None = None,
    extra: dict[str, object] | None = None,
) -> CompanyFacts:
    """Collect what is known. Anything absent stays None, never zero or a guess.

    `extra` carries facts that live outside the company row (website findings,
    review trends), so this function has one job and no hidden lookups.
    """
    owner = primary_owner(people or [])
    has_parent = True if corporate_directors(people or []) else None
    # No people on record means "unknown", not "no contact": the source may simply
    # never have been asked.
    named_people = [person for person in (people or []) if not person.is_company]
    has_named_contact = True if named_people else None
    values: dict[str, object] = {
        "name": company.display_name,
        "country": str(company.country),
        "industry_code": company.industry_code,
        "industry_label": company.industry_label,
        "founded_year": company.founded_year,
        "employee_count": employee_estimate(company),
        "revenue_low": company.revenue_low,
        "revenue_high": company.revenue_high,
        "owner_birth_year": owner.birth_year if owner else None,
        "has_parent_company": has_parent,
        "has_named_contact": has_named_contact,
    }
    values.update(extra or {})
    found_elsewhere = (extra or {}).get("evidence")
    values["evidence"] = {
        **_owner_evidence(owner),
        **(found_elsewhere if isinstance(found_elsewhere, dict) else {}),
    }
    return CompanyFacts(**values)


def _owner_evidence(owner: Person | None) -> dict[str, str]:
    """Who the birth year belongs to and where it came from, for the score reason."""
    if owner is None or owner.birth_year is None:
        return {}
    role = f" ({owner.role})" if owner.role else ""
    return {
        OWNER_BIRTH_YEAR: f"{owner.full_name}{role}, born {owner.birth_year}, "
        "from the company register"
    }
