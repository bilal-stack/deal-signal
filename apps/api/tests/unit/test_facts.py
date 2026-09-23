from __future__ import annotations

from datetime import UTC, datetime

from dealsignal.models.company import Company
from dealsignal.models.enums import Country, EmployeeBand, SourceName
from dealsignal.models.person import Person
from dealsignal.models.source import FieldValue
from dealsignal.services.facts import (
    best_by_field,
    build_company_facts,
    employee_estimate,
    primary_owner,
)


def company(**overrides: object) -> Company:
    defaults: dict[str, object] = {
        "display_name": "Craddock Lumber Co",
        "normalized_name": "craddock lumber",
        "country": Country.US,
    }
    return Company(**{**defaults, **overrides})


def person(**overrides: object) -> Person:
    defaults: dict[str, object] = {
        "full_name": "Pat Craddock",
        "is_owner": True,
        "source": SourceName.COMPANIES_HOUSE,
    }
    return Person(**{**defaults, **overrides})


def test_an_exact_headcount_wins_over_a_band() -> None:
    assert employee_estimate(company(employee_count=23, employee_band=EmployeeBand.B_50_99)) == 23


def test_a_band_becomes_its_midpoint() -> None:
    assert employee_estimate(company(employee_band=EmployeeBand.B_20_49)) == 35


def test_unknown_headcount_stays_unknown() -> None:
    assert employee_estimate(company()) is None


def test_the_owner_with_a_birth_year_is_preferred() -> None:
    known = person(full_name="Pat Craddock", birth_year=1958)
    unknown = person(full_name="Sam Craddock")

    assert primary_owner([unknown, known]) is known


def test_no_owner_returns_none() -> None:
    assert primary_owner([person(is_owner=False)]) is None


def test_facts_carry_what_is_known_and_nothing_more() -> None:
    facts = build_company_facts(
        company(founded_year=1996, revenue_low=3_000_000, revenue_high=5_000_000),
        people=[person(birth_year=1958)],
    )

    assert facts.founded_year == 1996
    assert facts.owner_birth_year == 1958
    assert facts.employee_count is None, "unknown must not become a guess"
    assert facts.has_recurring_revenue is None


def test_extra_findings_are_merged_in() -> None:
    facts = build_company_facts(
        company(),
        extra={
            "has_recurring_revenue": True,
            "evidence": {"has_recurring_revenue": "Annual plans"},
        },
    )

    assert facts.has_recurring_revenue is True
    assert facts.evidence["has_recurring_revenue"] == "Annual plans"


def test_an_owner_birth_year_says_whose_it_is_and_where_it_came_from() -> None:
    owner = person(full_name="Marie Durand", role="Gérant", birth_year=1958)

    facts = build_company_facts(company(), people=[owner])

    assert facts.evidence["owner_birth_year"] == (
        "Marie Durand (Gérant), born 1958, from the company register"
    )


def answer(field: str, value: object, confidence: float, day: int) -> FieldValue:
    return FieldValue(
        field=field,
        value=value,
        source=SourceName.WEBSITE,
        confidence=confidence,
        observed_at=datetime(2026, 9, day, tzinfo=UTC),
    )


def test_the_most_trusted_answer_wins_then_the_newest() -> None:
    register = answer("founded_year", 1996, confidence=0.95, day=1)
    website = answer("founded_year", 2001, confidence=0.6, day=17)
    older = answer("employee_count", 8, confidence=0.6, day=1)
    newer = answer("employee_count", 12, confidence=0.6, day=17)

    best = best_by_field([website, register, newer, older])

    assert best["founded_year"] is register, "a register outranks a newer website claim"
    assert best["employee_count"] is newer, "between equals, the newer answer wins"


def test_no_answers_means_no_fields() -> None:
    assert best_by_field([]) == {}
