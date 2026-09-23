"""Drafting a first message to a business owner from the facts already held.

The user does not have to describe the company: the brief comes from what we know,
and the draft cites it. The prompt keeps the tone low-key: this is someone's life's
work, not a conversion target.
"""

from __future__ import annotations

from typing import Literal

from anthropic import AsyncAnthropic
from pydantic import BaseModel, ConfigDict, Field

from dealsignal.ai.structured import StructuredCall, claude_client
from dealsignal.core.config import Settings

MODEL = "claude-opus-5"
EFFORT: Literal["medium"] = "medium"
MAX_TOKENS = 2048

MAX_SUBJECT_CHARS = 90
MAX_BODY_WORDS = 160

SYSTEM_PROMPT = """You write short first-contact messages on behalf of someone \
looking to buy a small business, or to sell services to one.

Rules:
- Use only the facts given. Never invent a detail about the company, and never \
imply you know something you were not told.
- Open with one concrete thing about this specific business. No flattery, no \
"I came across your website", no "I hope this finds you well".
- Plain words. No sales language, no urgency, no pressure, and never imply an \
offer or a valuation.
- Selling a business built over decades is a personal decision. Be respectful and \
low-key: the goal is a conversation, not a deal.
- Keep the body under 160 words, and write the way a person actually writes.
- End with a simple, low-commitment question."""

USER_TEMPLATE = """Write a first message to this company.

About the sender: {sender}
Purpose: {purpose}

The company:
{company}

What we know, and how we know it:
{facts}"""

PURPOSES = {
    "acquisition": (
        "The sender may want to buy a business like this one, and wants a first "
        "conversation with the owner. Do not make an offer."
    ),
    "sales": (
        "The sender wants to introduce what they sell and find out whether it is "
        "relevant. Do not pitch hard; ask whether it is worth a conversation."
    ),
}


class OutreachDraft(BaseModel):
    """A draft the user can read, edit and send themselves."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    subject: str = Field(description=f"Under {MAX_SUBJECT_CHARS} characters, plain and specific.")
    body: str = Field(description=f"Under {MAX_BODY_WORDS} words.")
    opening_fact: str = Field(
        description="The specific detail about this company that the message opens with."
    )
    follow_up: str = Field(description="A short, polite follow-up if there is no reply.")


class OutreachWriter:
    """Turns known facts into a draft message."""

    def __init__(self, settings: Settings, client: AsyncAnthropic | None = None) -> None:
        self._call = StructuredCall(
            claude_client(settings, client, needed_for="drafts cannot be written"),
            OutreachDraft,
            model=MODEL,
            effort=EFFORT,
            max_tokens=MAX_TOKENS,
            task="The draft writer",
        )

    async def write(self, *, company: str, facts: str, sender: str, purpose: str) -> OutreachDraft:
        return await self._call.ask(
            system=SYSTEM_PROMPT,
            user=USER_TEMPLATE.format(
                company=company, facts=facts, sender=sender, purpose=PURPOSES[purpose]
            ),
        )
