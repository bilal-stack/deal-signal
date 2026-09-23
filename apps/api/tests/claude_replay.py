"""Replaying recorded Claude replies, so tests never call or pay for the API.

A recording is made once with a script in `dealsignal.scripts`, which makes one real
call and saves the reply under tests/fixtures/claude. Here that reply is served by
an in-memory transport, so the real SDK parses a real response and our code handles
it exactly as it would in production.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx2
from anthropic import AsyncAnthropic

FIXTURES = Path(__file__).parent / "fixtures" / "claude"
NOT_A_KEY = "test-key-not-real"


def recorded(name: str) -> dict[str, Any]:
    fixture: dict[str, Any] = json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))
    return fixture


class ReplayedClaude:
    """An Anthropic client whose only network is one recorded reply."""

    def __init__(self, fixture_name: str) -> None:
        self.fixture = recorded(fixture_name)
        self.requests: list[dict[str, Any]] = []
        transport = httpx2.MockTransport(self._answer)
        self.client = AsyncAnthropic(
            api_key=NOT_A_KEY, max_retries=0, http_client=httpx2.AsyncClient(transport=transport)
        )

    def _answer(self, request: httpx2.Request) -> httpx2.Response:
        self.requests.append(json.loads(request.content))
        return httpx2.Response(200, json=self.fixture["response"])
