"""Outreach and do-not-contact schemas."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import Field

from dealsignal.models.enums import SuppressionKind
from dealsignal.schemas.common import ApiModel

MAX_BACKGROUND_CHARS = 500


class SenderInput(ApiModel):
    name: str = Field(min_length=1, max_length=120)
    background: str = Field(min_length=1, max_length=MAX_BACKGROUND_CHARS)


class DraftRequest(ApiModel):
    company_id: uuid.UUID
    buy_box_id: uuid.UUID | None = None
    """Used for the purpose (buying or selling) and the reasons the company scored."""

    sender: SenderInput


class DraftRead(ApiModel):
    company_id: str
    company_name: str
    subject: str
    body: str
    opening_fact: str
    follow_up: str
    facts_used: list[str]


class SuppressionAdd(ApiModel):
    kind: SuppressionKind = SuppressionKind.COMPANY
    value: str = Field(min_length=1, max_length=320)
    reason: str | None = Field(default=None, max_length=500)


class SuppressionRead(ApiModel):
    id: uuid.UUID
    kind: SuppressionKind
    value: str
    reason: str | None
    created_at: datetime
