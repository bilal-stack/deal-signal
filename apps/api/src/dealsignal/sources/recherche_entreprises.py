"""The French company register (API Recherche d'entreprises).

Free, open government data, no key. It gives the incorporation date, the industry
code, a headcount band and, most valuable for a buyer, each director's year of
birth, which is the strongest available hint that an owner may be ready to sell.
"""

from __future__ import annotations

from datetime import date
from typing import Any

import httpx

from dealsignal.core.config import Settings
from dealsignal.core.errors import ExternalServiceError, SourceBlockedError
from dealsignal.core.logging import get_logger
from dealsignal.models.enums import Country, SourceName
from dealsignal.sources.base import OfficerRecord, RegistryRecord, RegistrySource
from dealsignal.sources.registry_parsing import (
    MAX_OFFICERS,
    birth_year_from,
    employee_band_from_insee,
    is_same_company,
    looks_like_owner,
)

log = get_logger(__name__)

SEARCH_URL = "https://recherche-entreprises.api.gouv.fr/search"
RESULTS_PER_QUERY = 5
TIMEOUT_SECONDS = 15.0
ACTIVE = "A"


def _full_name(dirigeant: dict[str, Any]) -> str | None:
    """Directors come as separate given and family names, companies as one field."""
    if dirigeant.get("denomination"):
        return str(dirigeant["denomination"]).strip() or None
    parts = [dirigeant.get("prenoms"), _family_name(dirigeant.get("nom"))]
    name = " ".join(str(part).strip() for part in parts if part)
    return name.title() or None


def _family_name(raw: object) -> str | None:
    """The register writes "BIRTH (USAGE)". When both are the same, once is enough."""
    if not raw:
        return None
    text = str(raw).strip()
    birth, _, usage = text.partition(" (")
    if usage.endswith(")") and usage[:-1].strip().casefold() == birth.strip().casefold():
        return birth.strip()
    return text


def to_officers(payload: dict[str, Any]) -> tuple[OfficerRecord, ...]:
    """Directors, keeping only the year of birth."""
    officers: list[OfficerRecord] = []
    for dirigeant in payload.get("dirigeants") or []:
        if not isinstance(dirigeant, dict):
            continue
        name = _full_name(dirigeant)
        if not name:
            continue
        role = dirigeant.get("qualite")
        is_company = bool(dirigeant.get("denomination"))
        officers.append(
            OfficerRecord(
                full_name=name,
                role=role,
                birth_year=birth_year_from(dirigeant.get("annee_de_naissance")),
                is_owner=looks_like_owner(role),
                is_company=is_company,
            )
        )
    # Owners first, so the cap never discards the person who matters most.
    officers.sort(key=lambda officer: (not officer.is_owner, officer.full_name))
    return tuple(officers[:MAX_OFFICERS])


def to_registry_record(payload: dict[str, Any]) -> RegistryRecord | None:
    """Map one search result, or None when it is not usable."""
    siren = payload.get("siren")
    name = payload.get("nom_complet") or payload.get("nom_raison_sociale")
    if not siren or not name:
        return None

    created = payload.get("date_creation")
    incorporated = None
    if isinstance(created, str) and created.strip():
        try:
            incorporated = date.fromisoformat(created.strip())
        except ValueError:
            incorporated = None

    band = employee_band_from_insee(payload.get("tranche_effectif_salarie"))

    return RegistryRecord(
        source=SourceName.RECHERCHE_ENTREPRISES,
        registry_id=str(siren),
        legal_name=str(name),
        country=Country.FR,
        incorporated_on=incorporated,
        industry_code=payload.get("activite_principale"),
        status=payload.get("etat_administratif"),
        employee_band=str(band) if band else None,
        officers=to_officers(payload),
        raw={"siren": siren},
    )


class RechercheEntreprisesSource(RegistrySource):
    """Looks a French company up in the national register."""

    name = SourceName.RECHERCHE_ENTREPRISES
    countries = frozenset({Country.FR})

    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None) -> None:
        self._settings = settings
        self._client = client

    async def is_available(self) -> bool:
        """Open data with no key, so it is available whenever the network is."""
        return True

    async def lookup(
        self, *, name: str, country: Country, city: str | None = None
    ) -> RegistryRecord | None:
        if country is not Country.FR:
            return None

        client = self._client or httpx.AsyncClient(
            timeout=TIMEOUT_SECONDS,
            headers={"User-Agent": self._settings.crawler_user_agent},
        )
        close_client = self._client is None
        # The register matches names and places from one query string, so the town
        # is appended rather than sent as a separate filter.
        query = f"{name} {city}".strip() if city else name
        params: dict[str, str | int] = {"q": query, "per_page": RESULTS_PER_QUERY}

        try:
            response = await client.get(SEARCH_URL, params=params)
        except httpx.HTTPError as exc:
            raise ExternalServiceError(
                "The French company register did not answer.",
                source=SourceName.RECHERCHE_ENTREPRISES,
            ) from exc
        finally:
            if close_client:
                await client.aclose()

        if response.status_code == httpx.codes.TOO_MANY_REQUESTS:
            raise SourceBlockedError(
                "The French register is rate limiting us, so we backed off.",
                source=SourceName.RECHERCHE_ENTREPRISES,
            )
        if response.status_code >= httpx.codes.BAD_REQUEST:
            raise ExternalServiceError(
                f"The French register refused the request ({response.status_code}).",
                source=SourceName.RECHERCHE_ENTREPRISES,
            )

        results = response.json().get("results") or []
        for payload in results:
            record = to_registry_record(payload)
            if record is None or record.status != ACTIVE:
                continue
            if not is_same_company(name, record.legal_name):
                log.info(
                    "registry_rejected",
                    register="fr",
                    searched=name,
                    found=record.legal_name,
                    reason="name too different",
                )
                continue
            log.info("registry_match", register="fr", name=name, siren=record.registry_id)
            return record

        log.info("registry_no_match", register="fr", name=name)
        return None
