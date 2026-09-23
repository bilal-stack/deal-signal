"""Register payloads, including the partial dates and headcount bands."""

from __future__ import annotations

import pytest

from dealsignal.models.enums import EmployeeBand
from dealsignal.sources.registry_parsing import (
    birth_year_from,
    employee_band_from_insee,
    is_same_company,
    looks_like_owner,
)


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        ("02", EmployeeBand.B_1_9),
        ("11", EmployeeBand.B_10_19),
        ("12", EmployeeBand.B_20_49),
        ("22", EmployeeBand.B_100_249),
        ("53", EmployeeBand.B_250_PLUS),
    ],
)
def test_insee_codes_map_to_bands(code: str, expected: EmployeeBand) -> None:
    assert employee_band_from_insee(code) == expected


@pytest.mark.parametrize("code", [None, "", "NN", "00", "unknown"])
def test_no_headcount_on_record_stays_unknown(code: str | None) -> None:
    """ "No employees recorded" is not the same as "a small team"."""
    assert employee_band_from_insee(code) is None


def test_a_companies_house_birth_date_keeps_only_the_year() -> None:
    assert birth_year_from({"month": 4, "year": 1958}) == 1958


def test_a_plain_year_is_accepted_in_either_type() -> None:
    assert birth_year_from(1958) == 1958
    assert birth_year_from("1958") == 1958


@pytest.mark.parametrize("value", [None, "", "not a year", 12, 3025, {"month": 4}])
def test_nonsense_birth_years_are_rejected(value: object) -> None:
    assert birth_year_from(value) is None


@pytest.mark.parametrize(
    "role", ["director", "Gérant", "president", "LLP-Designated-Member", "Associé unique"]
)
def test_roles_that_can_sell_the_business_are_flagged(role: str) -> None:
    assert looks_like_owner(role) is True


@pytest.mark.parametrize("role", [None, "", "accountant", "auditor"])
def test_other_roles_are_not_owners(role: str | None) -> None:
    assert looks_like_owner(role) is False


def test_accented_roles_are_recognised() -> None:
    """The French register writes Président and Gérant; both can sell the business."""
    assert looks_like_owner("Président de SAS") is True
    assert looks_like_owner("Gérant") is True
    assert looks_like_owner("Directeur Général") is True


@pytest.mark.parametrize(
    "role",
    [
        "Commissaire aux comptes titulaire",
        "Contrôleur de gestion",
        "Administrateur",
        "Membre",
    ],
)
def test_supervisory_roles_are_not_owners(role: str) -> None:
    assert looks_like_owner(role) is False


@pytest.mark.parametrize(
    ("searched", "found"),
    [
        ("Arma Plomberie Chauffage Ventilation", "ARMA PLOMBERIE CHAUFFAGE VENTILATION"),
        ("Bodevigie", "ETABLISSEMENTS BODEVIGIE SAS"),
        ("Brunel Plomberie", "BRUNEL PLOMBERIE"),
    ],
)
def test_a_genuine_match_is_accepted(searched: str, found: str) -> None:
    assert is_same_company(searched, found) is True


@pytest.mark.parametrize(
    ("searched", "found"),
    [
        ("Atout Energie", "QUALITE ENTREPRISES"),
        ("CEDEO", "DISTRIBUTION SANITAIRE CHAUFFAGE (D.S.C.)"),
        ("Barou", "SOCIETE GENERALE"),
    ],
)
def test_a_different_company_is_rejected(searched: str, found: str) -> None:
    """A trade federation is not the company that shares part of its name."""
    assert is_same_company(searched, found) is False
