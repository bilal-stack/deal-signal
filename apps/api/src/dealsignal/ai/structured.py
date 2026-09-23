"""One Claude call whose reply must validate as a Pydantic model.

The website reader and the outreach writer need the same things: a fixed system
prompt worth caching, a response schema in the subset structured outputs accept, and
every way a call can end badly turned into an error a person can read. They get it
here, once.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Literal

from anthropic import APIError, AsyncAnthropic, transform_schema
from anthropic.types import Message, MessageParam, OutputConfigParam, TextBlockParam
from pydantic import BaseModel, ValidationError

from dealsignal.core.config import Settings
from dealsignal.core.errors import ExternalServiceError
from dealsignal.models.enums import SourceName

Effort = Literal["low", "medium", "high"]


def schema_fingerprint(schema: dict[str, Any]) -> str:
    """A stable hash of a JSON schema. A recorded reply stores the one it answered."""
    canonical = json.dumps(schema, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def claude_client(
    settings: Settings, client: AsyncAnthropic | None, *, needed_for: str
) -> AsyncAnthropic:
    """The injected client, or one built from the key, or a plain error saying why not."""
    if client is not None:
        return client
    if not settings.has_anthropic_key:
        raise ExternalServiceError(
            f"No Anthropic API key is configured, so {needed_for}. "
            "Set ANTHROPIC_API_KEY in your .env file.",
            source=SourceName.WEBSITE,
            retryable=False,
        )
    return AsyncAnthropic(api_key=settings.anthropic_api_key)


class StructuredCall[ReplyT: BaseModel]:
    """Asks Claude for one reply shaped like `reply`, or raises saying what went wrong.

    The schema goes through the SDK's `transform_schema`: structured outputs accept
    closed objects only, and range limits must live in descriptions. The reply is
    still validated against the full model, so nothing doubtful passes through.
    """

    def __init__(
        self,
        client: AsyncAnthropic,
        reply: type[ReplyT],
        *,
        model: str,
        effort: Effort,
        max_tokens: int,
        task: str,
    ) -> None:
        self._client = client
        self._reply = reply
        self._model = model
        self._effort = effort
        self._max_tokens = max_tokens
        self._task = task
        """Who is working, for the error messages: "The website reader"."""
        self.schema = transform_schema(reply)

    async def ask(self, *, system: str, user: str, details: dict[str, Any] | None = None) -> ReplyT:
        system_blocks: list[TextBlockParam] = [
            {"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}
        ]
        messages: list[MessageParam] = [{"role": "user", "content": user}]
        output_config: OutputConfigParam = {
            "effort": self._effort,
            "format": {"type": "json_schema", "schema": self.schema},
        }
        try:
            response = await self._client.messages.create(
                model=self._model,
                max_tokens=self._max_tokens,
                system=system_blocks,
                messages=messages,
                output_config=output_config,
            )
        except APIError as exc:
            raise ExternalServiceError(
                f"{self._task} could not finish: {exc}", source=SourceName.WEBSITE
            ) from exc
        return self._parse(response, details or {})

    def _parse(self, response: Message, details: dict[str, Any]) -> ReplyT:
        if response.stop_reason == "refusal":
            raise ExternalServiceError(
                f"{self._task} declined this request.",
                source=SourceName.WEBSITE,
                retryable=False,
                details=details,
            )
        if response.stop_reason == "max_tokens":
            raise ExternalServiceError(
                f"{self._task} ran out of room before finishing, so nothing was kept.",
                source=SourceName.WEBSITE,
                details=details,
            )
        text = "".join(block.text for block in response.content if block.type == "text")
        try:
            return self._reply.model_validate_json(text)
        except ValidationError as exc:
            raise ExternalServiceError(
                f"{self._task} returned something unreadable.",
                source=SourceName.WEBSITE,
                details=details,
            ) from exc
