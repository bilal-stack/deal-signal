"""Shared helpers for turning register payloads into RegistryRecords.

Registers publish headcount as a band and a director's date of birth as a partial
date. Both are mapped here, in one place, so the two country adapters stay thin
and the mapping is testable without a network call.
"""

from __future__ import annotations

import unicodedata

from dealsignal.matching.duplicates import name_similarity
from dealsignal.models.enums import EmployeeBand

INSEE_BANDS: dict[str, EmployeeBand] = {
    "01": EmployeeBand.B_1_9,
    "02": EmployeeBand.B_1_9,
    "03": EmployeeBand.B_1_9,
    "11": EmployeeBand.B_10_19,
    "12": EmployeeBand.B_20_49,
    "21": EmployeeBand.B_50_99,
    "22": EmployeeBand.B_100_249,
    "31": EmployeeBand.B_100_249,
    "32": EmployeeBand.B_250_PLUS,
    "41": EmployeeBand.B_250_PLUS,
    "42": EmployeeBand.B_250_PLUS,
    "51": EmployeeBand.B_250_PLUS,
    "52": EmployeeBand.B_250_PLUS,
    "53": EmployeeBand.B_250_PLUS,
}
"""INSEE headcount codes. "NN" and "00" mean no employees on record, which is not
the same as a small team, so they map to nothing."""

OWNER_ROLES: frozenset[str] = frozenset(
    {
        "president",
        "gerant",
        "directeur general",
        "associe",
        "proprietaire",
        "director",
        "secretary",
        "llp-designated-member",
        "llp-member",
    }
)
"""Roles held by someone who could actually sell the business. Compared without
accents, because the French register writes "Président" and "Gérant"."""

MINIMUM_NAME_SIMILARITY = 0.75
"""How close a register entry's name must be before we believe it is the same
business. Without this, a search for "Atout Energie" happily returns a national
federation with 1,958 directors, and every fact after that is wrong."""

MAX_OFFICERS = 25
"""A small business does not have more directors than this. A longer list means
we matched the wrong kind of entity."""


def employee_band_from_insee(code: str | None) -> EmployeeBand | None:
    """Map an INSEE headcount code, or None when the register does not say."""
    if not code:
        return None
    return INSEE_BANDS.get(code.strip())


def strip_accents(text: str) -> str:
    """'Président' -> 'president', so role matching works in both languages."""
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(character for character in decomposed if not unicodedata.combining(character))


def looks_like_owner(role: str | None) -> bool:
    """Whether a role suggests ownership rather than an administrative post."""
    if not role:
        return False
    normalised = strip_accents(role.strip().lower())
    return any(owner_role in normalised for owner_role in OWNER_ROLES)


def is_same_company(searched_name: str, register_name: str) -> bool:
    """Whether a register entry is close enough to be the company we asked about.

    Rejecting an uncertain match is the honest outcome: a missing register entry
    costs us confidence, while a wrong one silently corrupts the founding year,
    the owner and therefore the score.
    """
    return name_similarity(searched_name, register_name) >= MINIMUM_NAME_SIMILARITY


def birth_year_from(value: object) -> int | None:
    """Pull a four-digit year out of whatever shape the register used.

    Companies House gives {"month": 4, "year": 1958}; the French register gives a
    plain year. Only the year is ever kept, never the month.
    """
    if isinstance(value, dict):
        value = value.get("year")
    if isinstance(value, int):
        return value if 1900 <= value <= 2100 else None
    if isinstance(value, str) and value.strip().isdigit():
        year = int(value.strip())
        return year if 1900 <= year <= 2100 else None
    return None
