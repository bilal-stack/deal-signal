"""Industry taxonomy.

An industry is an explicit definition rather than a free-text match: the words people
type for it, the categories the data actually uses, and the official code it maps
to. `resolve` returns None for anything unknown, so callers can list what is
supported instead of guessing.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class Industry(BaseModel):
    """One industry, with everything needed to find it and label it."""

    model_config = ConfigDict(frozen=True)

    key: str
    label: str
    naics: str
    """US industry code, also used as the label for UK SIC / French NAF mapping."""

    aliases: frozenset[str]
    """What a user might type. Matched case-insensitively against the whole input."""

    categories: frozenset[str]
    """Category slugs exactly as they appear in the places data.

    Every slug below was verified against a real Overture release by counting
    occurrences in the Dallas-Fort Worth bounding box. Inventing a plausible slug
    is worse than useless: the query simply returns nothing, which looks identical
    to "there are no such businesses here"."""


INDUSTRIES: tuple[Industry, ...] = (
    Industry(
        key="hvac",
        label="HVAC",
        naics="238220",
        aliases=frozenset(
            {
                "hvac",
                "heating",
                "air conditioning",
                "ac repair",
                "heating and cooling",
                "heating and air conditioning",
                "furnace",
            }
        ),
        categories=frozenset({"hvac_services", "air_duct_cleaning_service"}),
    ),
    Industry(
        key="plumbing",
        label="Plumbing",
        naics="238220",
        aliases=frozenset({"plumbing", "plumber", "plumbers", "drainage"}),
        categories=frozenset({"plumbing"}),
    ),
    Industry(
        key="electrical",
        label="Electrical contracting",
        naics="238210",
        aliases=frozenset({"electrical", "electrician", "electricians", "electrical contractor"}),
        categories=frozenset({"electrician"}),
    ),
    Industry(
        key="landscaping",
        label="Landscaping",
        naics="561730",
        aliases=frozenset({"landscaping", "landscaper", "lawn care", "grounds maintenance"}),
        categories=frozenset({"landscaping", "landscape_architect"}),
    ),
    Industry(
        key="accounting",
        label="Accounting",
        naics="541211",
        aliases=frozenset({"accounting", "accountant", "accountants", "bookkeeping", "cpa"}),
        categories=frozenset({"accountant"}),
    ),
    Industry(
        key="dental",
        label="Dental practice",
        naics="621210",
        aliases=frozenset({"dental", "dentist", "dentists", "dental practice", "orthodontist"}),
        categories=frozenset({"general_dentistry", "cosmetic_dentist", "pediatric_dentist"}),
    ),
    Industry(
        key="veterinary",
        label="Veterinary practice",
        naics="541940",
        aliases=frozenset({"veterinary", "vet", "vets", "animal hospital", "veterinarian"}),
        categories=frozenset({"veterinarian"}),
    ),
    Industry(
        key="commercial_cleaning",
        label="Commercial cleaning",
        naics="561720",
        aliases=frozenset(
            {"cleaning", "commercial cleaning", "janitorial", "office cleaning", "cleaners"}
        ),
        categories=frozenset(
            {"office_cleaning", "cleaning_services", "b2b_cleaning_and_waste_management"}
        ),
    ),
)

_BY_KEY: dict[str, Industry] = {industry.key: industry for industry in INDUSTRIES}
_BY_ALIAS: dict[str, Industry] = {
    alias: industry for industry in INDUSTRIES for alias in industry.aliases
}


def resolve(text: str) -> Industry | None:
    """Find the industry a user meant, or None if we do not cover it.

    Matching is deliberately strict: an exact alias, or the whole input containing
    an alias as a phrase. Loose token matching is what turns "HVAC" into "Home
    Services" and then into a lumber yard.
    """
    needle = " ".join(text.lower().split())
    if not needle:
        return None
    if needle in _BY_KEY:
        return _BY_KEY[needle]
    if needle in _BY_ALIAS:
        return _BY_ALIAS[needle]
    for alias, industry in _BY_ALIAS.items():
        if f" {alias} " in f" {needle} ":
            return industry
    return None


def supported_labels() -> list[str]:
    """For error messages: what the user can actually ask for."""
    return sorted(industry.label for industry in INDUSTRIES)
