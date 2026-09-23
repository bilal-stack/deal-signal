"""Who counts as the owner, and what a corporate director tells us instead."""

from __future__ import annotations

from dealsignal.models.company import Company
from dealsignal.models.enums import Country, SourceName
from dealsignal.models.person import Person
from dealsignal.services.facts import build_company_facts, corporate_directors, primary_owner

REGISTER = SourceName.RECHERCHE_ENTREPRISES


def person(name: str, **overrides: object) -> Person:
    defaults: dict[str, object] = {"full_name": name, "is_owner": True, "source": REGISTER}
    return Person(**{**defaults, **overrides})


def company() -> Company:
    return Company(
        display_name="Chemisages du Sud-Est",
        normalized_name="chemisages du sud est",
        country=Country.FR,
    )


def test_a_holding_company_is_never_the_named_owner() -> None:
    """You cannot phone VENTIL DEVELOPPEMENT, and it will never retire."""
    people = [
        person("VENTIL DEVELOPPEMENT", is_company=True),
        person("Jean-Pierre Arma", birth_year=1964),
    ]

    owner = primary_owner(people)

    assert owner is not None
    assert owner.full_name == "Jean-Pierre Arma"


def test_no_human_owner_means_no_owner_rather_than_the_holding() -> None:
    assert primary_owner([person("MARSAL PARTICIPATIONS", is_company=True)]) is None


def test_the_person_with_a_birth_year_wins() -> None:
    people = [person("Sans Date"), person("Marie Durand", birth_year=1965)]

    owner = primary_owner(people)

    assert owner is not None
    assert owner.full_name == "Marie Durand"


def test_corporate_directors_are_listed_separately() -> None:
    people = [person("VENTIL DEVELOPPEMENT", is_company=True), person("Marie Durand")]

    assert [director.full_name for director in corporate_directors(people)] == [
        "VENTIL DEVELOPPEMENT"
    ]


def test_a_corporate_director_marks_the_company_as_having_a_parent() -> None:
    """Which costs it points for independence: a group-owned firm rarely sells."""
    facts = build_company_facts(company(), people=[person("VENTIL DEVELOPPEMENT", is_company=True)])

    assert facts.has_parent_company is True
    assert facts.owner_birth_year is None


def test_an_independent_company_does_not_claim_a_parent() -> None:
    facts = build_company_facts(company(), people=[person("Marie Durand", birth_year=1965)])

    assert facts.has_parent_company is None, "no evidence either way is not a claim"
    assert facts.owner_birth_year == 1965
