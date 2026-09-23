"""The UK company register (Companies House).

Two calls: find the company, then fetch its officers. The officers list is what
makes this worth doing, because it publishes each director's month and year of
birth. We keep the year only.

The API key is free but required, so this source reports itself unavailable
rather than failing a search when no key is configured.
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
    is_same_company,
    looks_like_owner,
)

log = get_logger(__name__)

BASE_URL = "https://api.company-information.service.gov.uk"
SEARCH_PATH = "/search/companies"
OFFICERS_PATH = "/company/{number}/officers"
RESULTS_PER_QUERY = 5
OFFICERS_PER_COMPANY = 20
TIMEOUT_SECONDS = 15.0
ACTIVE = "active"


def to_officers(payload: dict[str, Any]) -> tuple[OfficerRecord, ...]:
    """Directors, with resigned ones left out and only the birth year kept."""
    officers: list[OfficerRecord] = []
    for item in payload.get("items") or []:
        if not isinstance(item, dict) or item.get("resigned_on"):
            continue
        name = item.get("name")
        if not name:
            continue
        role = item.get("officer_role")
        appointed = item.get("appointed_on")
        officers.append(
            OfficerRecord(
                full_name=str(name),
                role=role,
                birth_year=birth_year_from(item.get("date_of_birth")),
                appointed_on=_parse_date(appointed),
                is_owner=looks_like_owner(role),
                is_company=str(role or "").lower().startswith("corporate"),
            )
        )
    officers.sort(key=lambda officer: (not officer.is_owner, officer.full_name))
    return tuple(officers[:MAX_OFFICERS])


def _parse_date(value: object) -> date | None:
    if isinstance(value, str) and value.strip():
        try:
            return date.fromisoformat(value.strip())
        except ValueError:
            return None
    return None


def to_registry_record(
    payload: dict[str, Any], officers: tuple[OfficerRecord, ...] = ()
) -> RegistryRecord | None:
    """Map one search hit, or None when it is unusable."""
    number = payload.get("company_number")
    title = payload.get("title") or payload.get("company_name")
    if not number or not title:
        return None

    sic_codes = payload.get("sic_codes") or []
    return RegistryRecord(
        source=SourceName.COMPANIES_HOUSE,
        registry_id=str(number),
        legal_name=str(title),
        country=Country.GB,
        incorporated_on=_parse_date(payload.get("date_of_creation")),
        industry_code=str(sic_codes[0]) if sic_codes else None,
        status=payload.get("company_status"),
        officers=officers,
        raw={"company_number": number},
    )


class CompaniesHouseSource(RegistrySource):
    """Looks a UK company up in Companies House."""

    name = SourceName.COMPANIES_HOUSE
    countries = frozenset({Country.GB})

    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None) -> None:
        self._settings = settings
        self._client = client

    async def is_available(self) -> bool:
        """False without a key, so a search skips it and says so."""
        return self._settings.has_companies_house_key or self._client is not None

    async def lookup(
        self, *, name: str, country: Country, city: str | None = None
    ) -> RegistryRecord | None:
        if country is not Country.GB:
            return None
        if not await self.is_available():
            raise ExternalServiceError(
                "No Companies House API key is configured, so UK register data was "
                "skipped. Add COMPANIES_HOUSE_API_KEY to enable it.",
                source=SourceName.COMPANIES_HOUSE,
                retryable=False,
            )

        client = self._client or httpx.AsyncClient(
            base_url=BASE_URL,
            timeout=TIMEOUT_SECONDS,
            auth=(self._settings.companies_house_api_key, ""),
            headers={"User-Agent": self._settings.crawler_user_agent},
        )
        close_client = self._client is None

        try:
            hits = await self._get(
                client, SEARCH_PATH, {"q": name, "items_per_page": RESULTS_PER_QUERY}
            )
            for payload in hits.get("items") or []:
                if payload.get("company_status") != ACTIVE:
                    continue
                found_name = str(payload.get("title") or payload.get("company_name") or "")
                if not is_same_company(name, found_name):
                    log.info("registry_rejected", register="uk", searched=name, found=found_name)
                    continue
                number = payload.get("company_number")
                officers = await self._officers(client, str(number)) if number else ()
                record = to_registry_record(payload, officers)
                if record is not None:
                    log.info("registry_match", register="uk", name=name, number=record.registry_id)
                    return record
        finally:
            if close_client:
                await client.aclose()

        log.info("registry_no_match", register="uk", name=name)
        return None

    async def _officers(self, client: httpx.AsyncClient, number: str) -> tuple[OfficerRecord, ...]:
        payload = await self._get(
            client, OFFICERS_PATH.format(number=number), {"items_per_page": OFFICERS_PER_COMPANY}
        )
        return to_officers(payload)

    async def _get(
        self, client: httpx.AsyncClient, path: str, params: dict[str, Any]
    ) -> dict[str, Any]:
        """One request, with the register's refusals named plainly."""
        try:
            response = await client.get(path, params=params)
        except httpx.HTTPError as exc:
            raise ExternalServiceError(
                "Companies House did not answer.", source=SourceName.COMPANIES_HOUSE
            ) from exc

        if response.status_code == httpx.codes.UNAUTHORIZED:
            raise ExternalServiceError(
                "Companies House rejected the API key.",
                source=SourceName.COMPANIES_HOUSE,
                retryable=False,
            )
        if response.status_code == httpx.codes.TOO_MANY_REQUESTS:
            raise SourceBlockedError(
                "Companies House is rate limiting us, so we backed off.",
                source=SourceName.COMPANIES_HOUSE,
            )
        if response.status_code >= httpx.codes.BAD_REQUEST:
            raise ExternalServiceError(
                f"Companies House refused the request ({response.status_code}).",
                source=SourceName.COMPANIES_HOUSE,
            )

        data: dict[str, Any] = response.json()
        return data
