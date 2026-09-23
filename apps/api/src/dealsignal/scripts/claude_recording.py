"""Recording one real Claude exchange, for tests to replay instead of calling the API.

Used by the record_* scripts. The client never retries, so a recording costs exactly
one call. Headers carry the API key, so they are never read, let alone stored.
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx2
from anthropic import AsyncAnthropic

from dealsignal.ai.structured import schema_fingerprint
from dealsignal.core.config import Settings

FIXTURES = Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "claude"
SUCCESS = 200
TIMEOUT_SECONDS = 120.0


class ExchangeRecorder:
    """Keeps each request body and response body the client exchanges."""

    def __init__(self) -> None:
        self.exchanges: list[tuple[dict[str, Any], int, dict[str, Any]]] = []

    async def __call__(self, response: httpx2.Response) -> None:
        await response.aread()
        request = json.loads(response.request.content or b"{}")
        self.exchanges.append((request, response.status_code, response.json()))

    def only_success(self) -> tuple[dict[str, Any], dict[str, Any]] | None:
        """The one exchange, if it happened and succeeded; otherwise say why not."""
        print(f"Claude calls made: {len(self.exchanges)}")  # noqa: T201
        if not self.exchanges:
            return None
        request, status, response = self.exchanges[0]
        if status != SUCCESS:
            print(f"The API answered {status}: {json.dumps(response)[:500]}", file=sys.stderr)  # noqa: T201
            return None
        return request, response


def recording_client(settings: Settings, recorder: ExchangeRecorder) -> AsyncAnthropic:
    return AsyncAnthropic(
        api_key=settings.anthropic_api_key,
        max_retries=0,
        http_client=httpx2.AsyncClient(
            timeout=TIMEOUT_SECONDS, event_hooks={"response": [recorder]}
        ),
    )


def request_summary(request: dict[str, Any]) -> dict[str, Any]:
    """The request described, not copied: enough to tell whether it has changed."""
    return {
        "model": request["model"],
        "max_tokens": request["max_tokens"],
        "effort": request["output_config"]["effort"],
        "schema_sha256": schema_fingerprint(request["output_config"]["format"]["schema"]),
    }


def save_fixture(name: str, *, script: str, response: dict[str, Any], **context: Any) -> Path:
    """Write the reply in full with its context. The reply is what cost money."""
    path = FIXTURES / f"{name}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    fixture = {
        "note": (
            f"One real Claude API response, recorded by scripts/{script}. "
            "Tests replay it instead of calling the API."
        ),
        "recorded_at": datetime.now(UTC).isoformat(timespec="seconds"),
        **context,
        "response": response,
    }
    path.write_text(json.dumps(fixture, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    usage = response.get("usage", {})
    print(  # noqa: T201
        f"Saved {path.name}: {usage.get('input_tokens')} tokens in, "
        f"{usage.get('output_tokens')} out."
    )
    return path
