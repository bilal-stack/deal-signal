"""A real outreach draft, recorded once and replayed: no network, no cost.

Written from the public facts held about one company. It proves the request is
accepted and the reply parses, and pins down what a first message must never contain.
"""

from __future__ import annotations

from anthropic import transform_schema

from dealsignal.ai.outreach import MAX_BODY_WORDS, MODEL, OutreachDraft, OutreachWriter
from dealsignal.ai.structured import schema_fingerprint
from dealsignal.core.config import Settings
from tests.claude_replay import ReplayedClaude

PRIVATE_DETAILS = ("born", "retire", "revenue", "$", "estimate", "not updated")


async def write_recorded() -> tuple[ReplayedClaude, OutreachDraft]:
    claude = ReplayedClaude("outreach_draft")
    draft = await OutreachWriter(Settings(environment="ci"), client=claude.client).write(
        company="A/C Service Co. (Fort Worth, TX)",
        facts="\n".join(f"- {fact}" for fact in claude.fixture["facts_used"]),
        sender="Alex Morgan. Runs a small search fund.",
        purpose="acquisition",
    )
    return claude, draft


async def test_the_reply_becomes_a_complete_draft() -> None:
    _, draft = await write_recorded()

    assert draft.subject and draft.body and draft.opening_fact and draft.follow_up
    assert len(draft.body.split()) <= MAX_BODY_WORDS


async def test_the_draft_opens_with_what_the_company_says_about_itself() -> None:
    _, draft = await write_recorded()

    assert "1999" in draft.body
    assert "family" in draft.body.lower()


async def test_nothing_private_reaches_the_owner() -> None:
    """Age, our revenue guess and a stale website help decide whom to write to; said to
    the owner, they read as surveillance."""
    _, draft = await write_recorded()

    text = f"{draft.subject} {draft.body} {draft.follow_up}".lower()
    assert not [word for word in PRIVATE_DETAILS if word in text]


async def test_one_request_is_sent_and_it_matches_the_recording() -> None:
    claude, _ = await write_recorded()

    [sent] = claude.requests
    assert sent["model"] == MODEL == claude.fixture["request"]["model"]
    assert sent["output_config"]["effort"] == claude.fixture["request"]["effort"]
    assert claude.fixture["request"]["schema_sha256"] == schema_fingerprint(
        transform_schema(OutreachDraft)
    ), "the draft schema changed after recording: re-record with record_outreach_draft"
