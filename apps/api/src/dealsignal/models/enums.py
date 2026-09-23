"""Enumerations shared by the models.

Stored as strings so a database dump stays readable and adding a value needs no
type migration dance.
"""

from __future__ import annotations

from enum import StrEnum


class Country(StrEnum):
    """Countries we cover."""

    US = "US"
    GB = "GB"
    FR = "FR"


class SourceName(StrEnum):
    """Every place a fact can come from. Stored with each value we keep."""

    OVERTURE = "overture"
    WEBSITE = "website"
    RDAP = "rdap"
    COMPANIES_HOUSE = "companies_house"
    RECHERCHE_ENTREPRISES = "recherche_entreprises"
    ESTIMATE = "estimate"
    """Derived by us, for example revenue from headcount. Never an observed fact."""


class EmployeeBand(StrEnum):
    """Headcount bands, because registries publish ranges, not exact numbers."""

    B_1_9 = "1-9"
    B_10_19 = "10-19"
    B_20_49 = "20-49"
    B_50_99 = "50-99"
    B_100_249 = "100-249"
    B_250_PLUS = "250+"


class DuplicateStatus(StrEnum):
    PENDING = "pending"
    MERGED = "merged"
    REJECTED = "rejected"


class BuyBoxMode(StrEnum):
    """What the user is looking for. The same companies, read two ways."""

    ACQUISITION = "acquisition"
    """Businesses whose owner may be ready to sell."""

    SALES = "sales"
    """Businesses likely to buy what the user sells."""


class PipelineStage(StrEnum):
    """Where a lead stands. Ordered as a deal normally moves."""

    NEW = "new"
    CONTACTED = "contacted"
    REPLIED = "replied"
    MEETING = "meeting"
    OFFER = "offer"
    WON = "won"
    LOST = "lost"


class SuppressionKind(StrEnum):
    """What a do-not-contact entry matches on."""

    COMPANY = "company"
    DOMAIN = "domain"


class EnrichmentTask(StrEnum):
    """A job that learns one thing about a company from an outside source."""

    DOMAIN_AGE = "domain_age"
    REGISTRY = "registry"
    WEBSITE = "website"
