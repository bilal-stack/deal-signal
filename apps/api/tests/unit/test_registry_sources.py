"""The two registers, with their HTTP mocked."""

from __future__ import annotations

import httpx
import pytest
import respx

from dealsignal.core.config import Settings
from dealsignal.core.errors import ExternalServiceError, SourceBlockedError
from dealsignal.models.enums import Country, SourceName
from dealsignal.sources.companies_house import CompaniesHouseSource
from dealsignal.sources.companies_house import to_officers as uk_officers
from dealsignal.sources.recherche_entreprises import RechercheEntreprisesSource, to_registry_record

FR_SEARCH = "https://recherche-entreprises.api.gouv.fr/search"
FR_RESULT = {
    "results": [
        {
            "siren": "552032534",
            "nom_complet": "CHAUFFAGE LYONNAIS",
            "date_creation": "1996-04-15",
            "activite_principale": "43.22B",
            "tranche_effectif_salarie": "12",
            "etat_administratif": "A",
            "dirigeants": [
                {
                    "nom": "Durand",
                    "prenoms": "Marie Claire",
                    "annee_de_naissance": "1958",
                    "qualite": "Gérant",
                },
                {"denomination": "HOLDING SAS", "qualite": "Président"},
            ],
        }
    ]
}


@pytest.fixture
def settings() -> Settings:
    return Settings(environment="ci")


def test_a_french_result_maps_across_with_the_owner_birth_year() -> None:
    record = to_registry_record(FR_RESULT["results"][0])

    assert record is not None
    assert record.source is SourceName.RECHERCHE_ENTREPRISES
    assert record.registry_id == "552032534"
    assert record.incorporated_on is not None
    assert record.incorporated_on.year == 1996
    assert record.employee_band == "20-49"
    director = next(o for o in record.officers if o.full_name == "Marie Claire Durand")
    assert director.birth_year == 1958
    assert director.is_owner is True


def test_a_corporate_director_keeps_its_company_name() -> None:
    record = to_registry_record(FR_RESULT["results"][0])

    assert record is not None
    holding = next(o for o in record.officers if o.full_name == "HOLDING SAS")
    assert holding.birth_year is None, "a company director has no birth year"


def test_a_result_without_a_siren_is_dropped() -> None:
    assert to_registry_record({"nom_complet": "No SIREN Ltd"}) is None


@respx.mock
async def test_the_french_register_returns_the_first_active_match(settings: Settings) -> None:
    respx.get(FR_SEARCH).mock(return_value=httpx.Response(200, json=FR_RESULT))

    record = await RechercheEntreprisesSource(settings).lookup(
        name="Chauffage Lyonnais", country=Country.FR, city="Lyon"
    )

    assert record is not None
    assert record.legal_name == "CHAUFFAGE LYONNAIS"


@respx.mock
async def test_no_match_is_none_not_an_error(settings: Settings) -> None:
    respx.get(FR_SEARCH).mock(return_value=httpx.Response(200, json={"results": []}))

    record = await RechercheEntreprisesSource(settings).lookup(
        name="Nothing Here", country=Country.FR
    )

    assert record is None


@respx.mock
async def test_rate_limiting_is_reported_as_blocked(settings: Settings) -> None:
    respx.get(FR_SEARCH).mock(return_value=httpx.Response(429))

    with pytest.raises(SourceBlockedError, match="rate limiting"):
        await RechercheEntreprisesSource(settings).lookup(name="X", country=Country.FR)


async def test_a_french_source_ignores_other_countries(settings: Settings) -> None:
    assert await RechercheEntreprisesSource(settings).lookup(name="X", country=Country.US) is None


async def test_companies_house_without_a_key_says_so(settings: Settings) -> None:
    source = CompaniesHouseSource(settings)

    assert await source.is_available() is False
    with pytest.raises(ExternalServiceError, match="COMPANIES_HOUSE_API_KEY"):
        await source.lookup(name="Any Ltd", country=Country.GB)


def test_uk_officers_keep_the_birth_year_and_drop_the_resigned() -> None:
    officers = uk_officers(
        {
            "items": [
                {
                    "name": "SMITH, John",
                    "officer_role": "director",
                    "date_of_birth": {"month": 4, "year": 1958},
                    "appointed_on": "1996-04-15",
                },
                {
                    "name": "JONES, Sara",
                    "officer_role": "director",
                    "resigned_on": "2019-01-01",
                },
            ]
        }
    )

    assert len(officers) == 1
    assert officers[0].full_name == "SMITH, John"
    assert officers[0].birth_year == 1958
    assert officers[0].appointed_on is not None
    assert officers[0].is_owner is True


@pytest.mark.parametrize(
    ("nom", "expected"),
    [
        ("BOULLANGER (BOULLANGER)", "Jerome Boullanger"),
        ("MARTIN (DURAND)", "Jerome Martin (Durand)"),
        ("BOULLANGER", "Jerome Boullanger"),
    ],
)
def test_a_repeated_usage_name_is_written_once(nom: str, expected: str) -> None:
    """The register gives "BIRTH (USAGE)". The same name twice is noise; two names are not."""
    result = {
        **FR_RESULT["results"][0],
        "dirigeants": [{"nom": nom, "prenoms": "JEROME", "qualite": "Gérant"}],
    }

    record = to_registry_record(result)

    assert record is not None
    assert [officer.full_name for officer in record.officers] == [expected]
