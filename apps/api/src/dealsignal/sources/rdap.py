"""Domain registration dates, via RDAP.

RDAP is the structured, keyless successor to WHOIS. Each domain extension has its
own registry service, and IANA publishes which one serves which extension (the
bootstrap file, RFC 9224). We read that file once a day and ask each registry
directly, rather than through the public redirector at rdap.org, which rate limits
heavily.

What a registration date proves is narrow, and the code keeps it that way: a
business with a domain registered in 2005 has been online at least since 2005. It
does not prove a business is young, because domains lapse and get re-registered.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from datetime import date, datetime
from enum import StrEnum
from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict

from dealsignal.core.cache import Cache, LocalCache
from dealsignal.core.config import Settings
from dealsignal.core.errors import ExternalServiceError, SourceBlockedError
from dealsignal.core.logging import get_logger
from dealsignal.models.enums import SourceName

log = get_logger(__name__)

BOOTSTRAP_URL = "https://data.iana.org/rdap/dns.json"
BOOTSTRAP_CACHE_KEY = "rdap:bootstrap"
BOOTSTRAP_TTL_SECONDS = 24 * 60 * 60
"""IANA changes the file when a registry moves its service, which is rare."""

CACHE_KEY = "rdap:{domain}"
CACHE_TTL_SECONDS = 30 * 24 * 60 * 60
"""A registration date does not change. Thirty days is conservative."""

RATE_LIMIT_KEY = "rdap:{host}"
MIN_INTERVAL_SECONDS = 0.5
TIMEOUT_SECONDS = 20.0
REGISTRATION_EVENT = "registration"

MAX_RETRIES = 2
DEFAULT_BACKOFF_SECONDS = 5.0
MAX_BACKOFF_SECONDS = 30.0
"""A registry that asks for a longer pause than this will not answer during this run."""


class RegistrationOutcome(StrEnum):
    """Why a lookup did or did not produce a date. Each one means something different."""

    FOUND = "found"
    NO_SERVICE = "no_service"
    """The extension's registry runs no RDAP service, so it publishes no dates."""
    NOT_REGISTERED = "not_registered"
    """The registry has no record of the domain: it has most likely lapsed."""
    NO_DATE = "no_date"
    """The registry answered without a registration date."""


class DomainRegistration(BaseModel):
    model_config = ConfigDict(frozen=True)

    outcome: RegistrationOutcome
    registered: date | None = None


def from_cache(cached: str) -> DomainRegistration:
    """A cached answer: an ISO date, an outcome name, or "" for an older entry."""
    if cached in RegistrationOutcome:
        return DomainRegistration(outcome=RegistrationOutcome(cached))
    if not cached:
        return DomainRegistration(outcome=RegistrationOutcome.NO_DATE)
    return DomainRegistration(
        outcome=RegistrationOutcome.FOUND, registered=date.fromisoformat(cached)
    )


def registration_date_from(payload: dict[str, Any]) -> date | None:
    """The domain's registration date from an RDAP response, if it states one."""
    for event in payload.get("events") or []:
        if not isinstance(event, dict) or event.get("eventAction") != REGISTRATION_EVENT:
            continue
        raw = event.get("eventDate")
        if not isinstance(raw, str):
            return None
        try:
            return datetime.fromisoformat(raw.replace("Z", "+00:00")).date()
        except ValueError:
            return None
    return None


def registry_urls_from(bootstrap: dict[str, Any]) -> dict[str, str]:
    """Each extension's RDAP service, from IANA's bootstrap file.

    Every entry pairs a list of extensions with a list of service URLs. HTTPS is
    preferred, and each URL ends in a slash so paths can be appended to it.
    """
    services: dict[str, str] = {}
    for entry in bootstrap.get("services") or []:
        if not isinstance(entry, list) or len(entry) < 2:
            continue
        extensions, urls = entry[0], entry[1]
        usable = [url for url in urls if isinstance(url, str)]
        secure = [url for url in usable if url.startswith("https://")]
        if not usable:
            continue
        chosen = (secure or usable)[0]
        base = chosen if chosen.endswith("/") else f"{chosen}/"
        for extension in extensions:
            if isinstance(extension, str):
                services[extension.lower()] = base
    return services


def retry_after_seconds(response: httpx.Response) -> float:
    """How long the server asked us to wait, within reason, or a default pause."""
    try:
        requested = float(response.headers.get("Retry-After", ""))
    except ValueError:
        # Absent, or given as an HTTP date. Neither is worth parsing for one pause.
        requested = DEFAULT_BACKOFF_SECONDS
    return min(max(requested, 0.0), MAX_BACKOFF_SECONDS)


class RdapSource:
    """Looks up when a website domain was first registered."""

    name = SourceName.RDAP

    def __init__(
        self,
        settings: Settings,
        client: httpx.AsyncClient | None = None,
        cache: Cache | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self._settings = settings
        self._client = client
        self._cache = cache or LocalCache()
        self._sleep = sleep
        self._registries: dict[str, str] | None = None

    async def lookup(self, domain: str) -> DomainRegistration:
        """The registration date, or the reason there is none.

        No service, no record, or no date are answers, not errors. A rate limit that
        outlasts our retries, or an unreachable service, is an error, and says so.
        """
        cached = await self._cache.get(CACHE_KEY.format(domain=domain))
        if isinstance(cached, str):
            return from_cache(cached)

        async with self._http() as client:
            base_url = await self._registry_for(client, domain)
            if base_url is None:
                log.info("rdap_no_service", domain=domain)
                return await self._remember(domain, RegistrationOutcome.NO_SERVICE)
            response = await self._get(client, f"{base_url}domain/{domain}")

        if response.status_code == httpx.codes.NOT_FOUND:
            log.info("rdap_not_registered", domain=domain)
            return await self._remember(domain, RegistrationOutcome.NOT_REGISTERED)
        if response.status_code == httpx.codes.TOO_MANY_REQUESTS:
            raise SourceBlockedError(
                f"The registry for {domain} was still rate limiting us after "
                f"{MAX_RETRIES} pauses and retries. Run the job again later.",
                source=SourceName.RDAP,
            )
        if response.status_code >= httpx.codes.BAD_REQUEST:
            raise ExternalServiceError(
                f"The registry for {domain} refused the request ({response.status_code}).",
                source=SourceName.RDAP,
            )

        registered = registration_date_from(self._json(response))
        if registered is None:
            return await self._remember(domain, RegistrationOutcome.NO_DATE)
        return await self._remember(domain, RegistrationOutcome.FOUND, registered)

    async def _registry_for(self, client: httpx.AsyncClient, domain: str) -> str | None:
        """The RDAP service for this domain's extension, or None if it has none."""
        if self._registries is None:
            self._registries = await self._load_registries(client)
        extension = domain.rsplit(".", 1)[-1].lower()
        return self._registries.get(extension)

    async def _load_registries(self, client: httpx.AsyncClient) -> dict[str, str]:
        cached = await self._cache.get(BOOTSTRAP_CACHE_KEY)
        if isinstance(cached, dict) and cached:
            return cached

        response = await self._get(client, BOOTSTRAP_URL)
        if response.status_code >= httpx.codes.BAD_REQUEST:
            raise ExternalServiceError(
                f"IANA's list of domain registries did not load ({response.status_code}).",
                source=SourceName.RDAP,
            )
        registries = registry_urls_from(self._json(response))
        if registries:
            await self._cache.set(BOOTSTRAP_CACHE_KEY, registries, BOOTSTRAP_TTL_SECONDS)
        return registries

    async def _get(self, client: httpx.AsyncClient, url: str) -> httpx.Response:
        """One paced request per service, pausing and retrying when told to slow down.

        The pause is what the server asked for (Retry-After), within reason. The
        caller decides what a response that is still 429 afterwards means.
        """
        host = httpx.URL(url).host
        retries = 0
        while True:
            await self._cache.wait_for_turn(RATE_LIMIT_KEY.format(host=host), MIN_INTERVAL_SECONDS)
            try:
                response = await client.get(url)
            except httpx.HTTPError as exc:
                raise ExternalServiceError(
                    f"The registry service at {host} did not answer.", source=SourceName.RDAP
                ) from exc

            if response.status_code != httpx.codes.TOO_MANY_REQUESTS or retries >= MAX_RETRIES:
                return response
            retries += 1
            pause = retry_after_seconds(response)
            log.info("rdap_backing_off", host=host, seconds=pause, retry=retries)
            await self._sleep(pause)

    @asynccontextmanager
    async def _http(self) -> AsyncIterator[httpx.AsyncClient]:
        """The injected client, or a fresh one that is closed afterwards."""
        if self._client is not None:
            yield self._client
            return
        async with httpx.AsyncClient(
            timeout=TIMEOUT_SECONDS,
            follow_redirects=True,
            headers={
                "User-Agent": self._settings.crawler_user_agent,
                "Accept": "application/rdap+json, application/json",
            },
        ) as client:
            yield client

    @staticmethod
    def _json(response: httpx.Response) -> dict[str, Any]:
        """The response body as an object, or a plain-language error."""
        try:
            payload = response.json()
        except ValueError:
            payload = None
        if not isinstance(payload, dict):
            raise ExternalServiceError(
                "The registry service returned something unreadable.", source=SourceName.RDAP
            )
        return payload

    async def _remember(
        self, domain: str, outcome: RegistrationOutcome, registered: date | None = None
    ) -> DomainRegistration:
        """Cache the answer, including the ones without a date, so we stop re-asking."""
        await self._cache.set(
            CACHE_KEY.format(domain=domain),
            registered.isoformat() if registered else outcome.value,
            CACHE_TTL_SECONDS,
        )
        return DomainRegistration(outcome=outcome, registered=registered)
