"""A real Claude reply, recorded once and replayed: no network, no cost.

The recording is one website read (A/C Service Co., Fort Worth). It proves the request
is accepted and the reply parses, which a hand-written fake cannot.
"""

from __future__ import annotations

from dealsignal.ai.extractor import MODEL, RESPONSE_SCHEMA, WebsiteExtractor
from dealsignal.ai.schemas import WebsiteFacts
from dealsignal.ai.structured import schema_fingerprint
from dealsignal.core.config import Settings
from tests.claude_replay import ReplayedClaude

PAGES = {"http://checkmyac.com": "Any text: the reply is replayed, not generated."}


async def read_recorded() -> tuple[ReplayedClaude, WebsiteFacts]:
    claude = ReplayedClaude("website_read")
    facts = await WebsiteExtractor(Settings(environment="ci"), client=claude.client).extract(
        company_name="A/C Service Co.", url="http://checkmyac.com", pages=PAGES
    )
    return claude, facts


async def test_the_reply_becomes_facts_each_with_its_quote() -> None:
    _, facts = await read_recorded()

    assert facts.known_fields() == {
        "founded_year": 1999,
        "mentions_family_ownership": True,
        "sells_to_businesses": True,
        "has_recurring_revenue": True,
    }
    assert facts.quote_for("has_recurring_revenue") == (
        "We offer commercial and residential preventative maintenance agreements."
    )
    assert all(facts.quote_for(name) for name in facts.known_fields())


async def test_what_the_site_does_not_say_stays_unknown() -> None:
    _, facts = await read_recorded()

    assert facts.employee_count is None, "no headcount on the site, so none was guessed"
    assert facts.owner_name is None


async def test_one_request_is_sent_and_it_matches_the_recording() -> None:
    claude, _ = await read_recorded()

    [sent] = claude.requests
    assert sent["model"] == MODEL == claude.fixture["request"]["model"]
    assert sent["output_config"]["effort"] == claude.fixture["request"]["effort"]
    assert sent["output_config"]["format"] == {"type": "json_schema", "schema": RESPONSE_SCHEMA}
    assert sent["system"][0]["cache_control"] == {"type": "ephemeral"}


def test_the_recording_answers_the_schema_we_send_today() -> None:
    """If this fails, the extraction schema changed after the reply was recorded, so
    the replay no longer proves the API accepts it. Re-record with one call:
    python -m dealsignal.scripts.record_website_read --company <id>"""
    recorded = ReplayedClaude("website_read").fixture["request"]["schema_sha256"]

    assert recorded == schema_fingerprint(RESPONSE_SCHEMA)
