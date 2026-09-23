"""Pacing and caching: the promise we make to servers we do not own."""

from __future__ import annotations

import asyncio
import time

import httpx
import pytest
import respx

from dealsignal.core.cache import LocalCache
from dealsignal.core.config import Settings
from dealsignal.sources.rdap import BOOTSTRAP_URL, RdapSource

REGISTRY_URL = "https://rdap.verisign.com/com/v1/domain/example.com"
RDAP_RESPONSE = {"events": [{"eventAction": "registration", "eventDate": "2005-04-09T07:40:00Z"}]}


async def test_the_second_request_waits_its_turn() -> None:
    cache = LocalCache()
    interval = 0.2

    started = time.monotonic()
    await cache.wait_for_turn("example.com", interval)
    await cache.wait_for_turn("example.com", interval)
    elapsed = time.monotonic() - started

    assert elapsed >= interval


async def test_different_domains_do_not_wait_for_each_other() -> None:
    cache = LocalCache()

    started = time.monotonic()
    await asyncio.gather(
        cache.wait_for_turn("one.example", 0.3), cache.wait_for_turn("two.example", 0.3)
    )

    assert time.monotonic() - started < 0.3


async def test_a_cached_value_comes_back_until_it_expires() -> None:
    cache = LocalCache()
    await cache.set("key", {"value": 1}, ttl_seconds=60)

    assert await cache.get("key") == {"value": 1}


async def test_an_expired_value_is_gone() -> None:
    cache = LocalCache()
    await cache.set("key", "value", ttl_seconds=0)
    await asyncio.sleep(0.01)

    assert await cache.get("key") is None


def registries_known() -> None:
    respx.get(BOOTSTRAP_URL).mock(
        return_value=httpx.Response(
            200, json={"services": [[["com"], ["https://rdap.verisign.com/com/v1/"]]]}
        )
    )


@respx.mock
async def test_a_domain_is_only_looked_up_once() -> None:
    registries_known()
    route = respx.get(REGISTRY_URL).mock(return_value=httpx.Response(200, json=RDAP_RESPONSE))
    source = RdapSource(Settings(environment="ci"), cache=LocalCache())

    first = await source.lookup("example.com")
    second = await source.lookup("example.com")

    assert first == second
    assert first.registered is not None
    assert route.call_count == 1, "the second answer came from the cache"


@respx.mock
async def test_not_published_is_remembered_too() -> None:
    """Otherwise every run re-asks about the same domains that will never answer."""
    registries_known()
    route = respx.get(REGISTRY_URL).mock(return_value=httpx.Response(404))
    source = RdapSource(Settings(environment="ci"), cache=LocalCache())

    assert (await source.lookup("example.com")).registered is None
    assert (await source.lookup("example.com")).registered is None
    assert route.call_count == 1


@pytest.mark.parametrize("value", [None, ""])
async def test_missing_keys_read_as_missing(value: str | None) -> None:
    cache = LocalCache()

    assert await cache.get("never-set") is None
