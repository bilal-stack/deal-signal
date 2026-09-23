"""Domain age: what a registration date proves, and what it does not."""

from __future__ import annotations

from datetime import date

import httpx
import pytest
import respx

from dealsignal.core.config import Settings
from dealsignal.core.errors import SourceBlockedError
from dealsignal.models.company import Company
from dealsignal.scoring.context import BuyBoxCriteria, CompanyFacts, ScoringContext
from dealsignal.scoring.signals.tenure import YearsInBusinessSignal
from dealsignal.services.domain_age import DomainAgeService
from dealsignal.sources.rdap import (
    MAX_BACKOFF_SECONDS,
    MAX_RETRIES,
    DomainRegistration,
    RdapSource,
    RegistrationOutcome,
    from_cache,
    registration_date_from,
    registry_urls_from,
)

TODAY = date(2026, 9, 17)


def context(**facts: object) -> ScoringContext:
    return ScoringContext(
        facts=CompanyFacts(name="Test Co", country="US", **facts),
        criteria=BuyBoxCriteria(),
        today=TODAY,
    )


def test_the_registration_event_is_read() -> None:
    payload = {
        "events": [
            {"eventAction": "last changed", "eventDate": "2024-01-01T00:00:00Z"},
            {"eventAction": "registration", "eventDate": "2005-04-09T07:40:00Z"},
        ]
    }

    assert registration_date_from(payload) == date(2005, 4, 9)


@pytest.mark.parametrize(
    "payload",
    [{}, {"events": []}, {"events": [{"eventAction": "registration", "eventDate": "garbage"}]}],
)
def test_a_missing_or_broken_date_is_unknown(payload: dict[str, object]) -> None:
    assert registration_date_from(payload) is None


def test_an_old_domain_counts_as_a_lower_bound_on_age() -> None:
    result = YearsInBusinessSignal().evaluate(context(domain_registered_year=2000))

    assert result is not None
    assert result.points == result.max_points
    assert "domain registered in 2000" in result.reason
    assert "at least 26 years" in result.reason


def test_a_recent_domain_proves_nothing_and_abstains() -> None:
    """a11air.com was registered in 2026. That does not make the business new."""
    assert YearsInBusinessSignal().evaluate(context(domain_registered_year=2026)) is None


def test_a_real_founding_year_always_wins_over_the_domain() -> None:
    result = YearsInBusinessSignal().evaluate(
        context(founded_year=2015, domain_registered_year=1998)
    )

    assert result is not None
    assert "Founded 2015" in result.reason


IANA = "https://data.iana.org/rdap/dns.json"
BOOTSTRAP = {
    "services": [
        [["com", "net"], ["https://rdap.verisign.com/com/v1/"]],
        [["uk"], ["http://rdap.nominet.uk/uk", "https://rdap.nominet.uk/uk"]],
    ]
}


def registered_on(iso: str) -> httpx.Response:
    return httpx.Response(200, json={"events": [{"eventAction": "registration", "eventDate": iso}]})


def rdap(pauses: list[float] | None = None) -> RdapSource:
    """A source whose back-off pauses are recorded instead of slept."""

    async def sleep(seconds: float) -> None:
        if pauses is not None:
            pauses.append(seconds)

    return RdapSource(Settings(environment="ci"), sleep=sleep)


def test_each_extension_maps_to_its_own_registry() -> None:
    registries = registry_urls_from(BOOTSTRAP)

    assert registries["com"] == "https://rdap.verisign.com/com/v1/"
    assert registries["uk"] == "https://rdap.nominet.uk/uk/", "https preferred, slash added"


@respx.mock
async def test_the_registry_is_asked_directly() -> None:
    """Each extension's own registry answers, not the shared redirector."""
    respx.get(IANA).mock(return_value=httpx.Response(200, json=BOOTSTRAP))
    registry = respx.get("https://rdap.nominet.uk/uk/domain/example.co.uk").mock(
        return_value=registered_on("2004-02-06T00:00:00Z")
    )

    assert (await rdap().lookup("example.co.uk")).registered == date(2004, 2, 6)
    assert registry.called


@respx.mock
async def test_an_extension_without_a_registry_is_unknown_not_an_error() -> None:
    # Any request respx has not been told about fails the test, so no registry is asked.
    respx.get(IANA).mock(return_value=httpx.Response(200, json=BOOTSTRAP))

    assert (await rdap().lookup("example.xyz")).registered is None


@respx.mock
async def test_the_list_of_registries_is_loaded_once() -> None:
    iana = respx.get(IANA).mock(return_value=httpx.Response(200, json=BOOTSTRAP))
    respx.get(url__regex=r"https://rdap\.verisign\.com/com/v1/domain/.+").mock(
        return_value=httpx.Response(404)
    )
    lookups = rdap()

    await lookups.lookup("first.com")
    await lookups.lookup("second.com")

    assert iana.call_count == 1


@respx.mock
async def test_a_rate_limit_is_waited_out_then_retried() -> None:
    respx.get(IANA).mock(return_value=httpx.Response(200, json=BOOTSTRAP))
    respx.get("https://rdap.verisign.com/com/v1/domain/example.com").mock(
        side_effect=[
            httpx.Response(429, headers={"Retry-After": "3"}),
            registered_on("2005-04-09T07:40:00Z"),
        ]
    )
    pauses: list[float] = []

    assert (await rdap(pauses).lookup("example.com")).registered == date(2005, 4, 9)
    assert pauses == [3.0], "the pause is the one the registry asked for"


@respx.mock
async def test_a_rate_limit_that_persists_is_reported_as_it_happened() -> None:
    respx.get(IANA).mock(return_value=httpx.Response(200, json=BOOTSTRAP))
    registry = respx.get("https://rdap.verisign.com/com/v1/domain/example.com").mock(
        return_value=httpx.Response(429, headers={"Retry-After": "600"})
    )
    pauses: list[float] = []

    with pytest.raises(SourceBlockedError, match="still rate limiting us after 2 pauses"):
        await rdap(pauses).lookup("example.com")

    assert registry.call_count == MAX_RETRIES + 1
    assert pauses == [MAX_BACKOFF_SECONDS] * MAX_RETRIES, "a ten-minute request is capped"


@respx.mock
async def test_a_domain_the_registry_does_not_know_is_reported_as_lapsed() -> None:
    """A 404 from the registry means no such registration, not "no date published"."""
    respx.get(IANA).mock(return_value=httpx.Response(200, json=BOOTSTRAP))
    respx.get("https://rdap.verisign.com/com/v1/domain/gone.com").mock(
        return_value=httpx.Response(404)
    )
    service = DomainAgeService(session=None, source=rdap(), shared_domains=frozenset())  # type: ignore[arg-type]
    company = Company(
        display_name="Gone Co", normalized_name="gone", country="US", domain="gone.com"
    )

    outcome = await service.enrich(company)

    assert outcome.succeeded is False
    assert outcome.message == (
        "The registry has no record of gone.com, so the domain has probably lapsed."
    )


@respx.mock
async def test_an_extension_without_a_registry_service_says_so() -> None:
    respx.get(IANA).mock(return_value=httpx.Response(200, json=BOOTSTRAP))
    service = DomainAgeService(session=None, source=rdap(), shared_domains=frozenset())  # type: ignore[arg-type]
    company = Company(display_name="Co Co", normalized_name="co", country="US", domain="aura.co")

    outcome = await service.enrich(company)

    assert outcome.message == "Registries for .co domains do not publish dates."


@pytest.mark.parametrize(
    ("cached", "expected"),
    [
        (
            "2005-04-09",
            DomainRegistration(outcome=RegistrationOutcome.FOUND, registered=date(2005, 4, 9)),
        ),
        ("not_registered", DomainRegistration(outcome=RegistrationOutcome.NOT_REGISTERED)),
        ("", DomainRegistration(outcome=RegistrationOutcome.NO_DATE)),
    ],
)
def test_cached_answers_keep_their_reason(cached: str, expected: DomainRegistration) -> None:
    """An empty cached value is an older entry, and reads as the vaguest outcome."""
    assert from_cache(cached) == expected
