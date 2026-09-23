"""The extraction schema, especially its handling of what is not known."""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from dealsignal.ai.extractor import RESPONSE_SCHEMA
from dealsignal.ai.prompts import build_user_message
from dealsignal.ai.schemas import FACT_NAMES, MAX_EVIDENCE_CHARS, Evidence, WebsiteFacts

PROSE_FIELDS = {"summary", "services", "opening_line", "evidence"}


def test_a_sparse_result_is_valid() -> None:
    """A site that says little must produce nulls, not a validation error."""
    facts = WebsiteFacts(summary="A plumbing company in Dallas.")

    assert facts.founded_year is None
    assert facts.owner_name is None
    assert facts.has_recurring_revenue is None
    assert facts.known_fields() == {}


def test_known_fields_exclude_prose_and_only_carry_facts() -> None:
    facts = WebsiteFacts(
        summary="Family plumbing business.",
        services=["Drain cleaning"],
        founded_year=1996,
        mentions_family_ownership=True,
        opening_line="You have served Dallas since 1996.",
    )

    assert facts.known_fields() == {
        "founded_year": 1996,
        "mentions_family_ownership": True,
    }


def test_every_fact_can_be_quoted_and_every_quotable_name_is_a_fact() -> None:
    """The evidence names are an enum the model must pick from; they cannot drift."""
    assert set(FACT_NAMES) == set(WebsiteFacts.model_fields) - PROSE_FIELDS


def test_a_quote_is_found_by_the_fact_it_supports() -> None:
    facts = WebsiteFacts(
        summary="x",
        founded_year=1996,
        evidence=[Evidence(fact="founded_year", quote="Serving Dallas since 1996.")],
    )

    assert facts.quote_for("founded_year") == "Serving Dallas since 1996."
    assert facts.quote_for("employee_count") is None


@pytest.mark.parametrize("year", [1200, 2999])
def test_an_implausible_founding_year_becomes_unknown(year: int) -> None:
    """A misread year is dropped on its own; the rest of the read is kept."""
    facts = WebsiteFacts(summary="x", founded_year=year, owner_name="Pat")

    assert facts.founded_year is None
    assert facts.owner_name == "Pat"


@pytest.mark.parametrize("field", ["location_count", "employee_count"])
def test_a_count_of_zero_becomes_unknown(field: str) -> None:
    facts = WebsiteFacts.model_validate({"summary": "x", field: 0})

    assert getattr(facts, field) is None


def test_a_long_quote_is_shortened_not_refused() -> None:
    sentence = "Family owned and operated since 1996, " * 20

    quote = Evidence(fact="founded_year", quote=sentence).quote

    assert len(quote) == MAX_EVIDENCE_CHARS
    assert quote.endswith("…")
    assert sentence.startswith(quote[:-1]), "what is kept is still word for word"


def test_unexpected_fields_are_refused() -> None:
    with pytest.raises(ValidationError):
        WebsiteFacts(summary="x", revenue=5_000_000)  # type: ignore[call-arg]


def walk(schema: Any) -> list[dict[str, Any]]:
    """Every object node in a JSON schema."""
    if isinstance(schema, dict):
        return [schema, *(node for value in schema.values() for node in walk(value))]
    if isinstance(schema, list):
        return [node for value in schema for node in walk(value)]
    return []


def test_the_schema_sent_to_claude_is_in_the_accepted_shape() -> None:
    """Structured outputs accept closed objects only. A map of evidence was silently
    turned into an object that allows no keys, so every quote would have been lost."""
    nodes = walk(RESPONSE_SCHEMA)
    objects = [node for node in nodes if node.get("type") == "object"]

    assert objects, "the schema has objects to check"
    assert all(node.get("additionalProperties") is False for node in objects)
    assert not any({"minimum", "maximum", "maxLength"} & node.keys() for node in nodes)

    evidence = RESPONSE_SCHEMA["properties"]["evidence"]
    assert evidence["type"] == "array"
    item = RESPONSE_SCHEMA["$defs"]["Evidence"]
    assert set(item["properties"]["fact"]["enum"]) == set(FACT_NAMES)


def test_the_user_message_labels_every_page() -> None:
    message = build_user_message(
        company_name="Baker Brothers",
        url="https://example.com",
        pages={"https://example.com": "Home text", "https://example.com/about": "About text"},
    )

    assert "PAGE: https://example.com/about" in message
    assert "About text" in message
    assert "Baker Brothers" in message
