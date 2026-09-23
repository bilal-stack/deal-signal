"""The batch runner: counts honestly and keeps the reasons for failures."""

from __future__ import annotations

from dataclasses import dataclass

from dealsignal.models.company import Company
from dealsignal.models.enums import Country
from dealsignal.workers.batch import MAX_REPORTED_FAILURES, Outcome, run_batch


@dataclass(frozen=True)
class FakeOutcome:
    succeeded: bool
    message: str


def company(name: str) -> Company:
    return Company(display_name=name, normalized_name=name.lower(), country=Country.US)


async def test_successes_and_failures_are_both_counted() -> None:
    companies = [company("Old Domain Co"), company("No Domain Co"), company("Another Old Co")]

    async def enrich(item: Company) -> FakeOutcome:
        if item.display_name == "No Domain Co":
            return FakeOutcome(False, "No website domain on record to look up.")
        return FakeOutcome(True, "Domain registered 2005-04-09.")

    report = await run_batch("check_domain_age", companies, enrich)

    assert report.attempted == 3
    assert report.succeeded == 2
    assert report.failed == 1
    assert report.failures[0].company == "No Domain Co"
    assert "No website domain" in report.failures[0].reason


async def test_the_failure_list_is_capped_but_the_count_is_not() -> None:
    companies = [company(f"Company {index}") for index in range(MAX_REPORTED_FAILURES + 10)]

    async def enrich(item: Company) -> FakeOutcome:
        return FakeOutcome(False, "Blocked.")

    report = await run_batch("read_websites", companies, enrich)

    assert len(report.failures) == MAX_REPORTED_FAILURES
    assert report.failed == MAX_REPORTED_FAILURES + 10, "the true count is never truncated"


async def test_an_empty_batch_is_an_honest_zero() -> None:
    async def enrich(item: Company) -> FakeOutcome:
        raise AssertionError("should not be called")

    report = await run_batch("lookup_registry", [], enrich)

    assert report.attempted == 0
    assert report.failures == []


async def test_each_result_is_saved_as_soon_as_it_is_known() -> None:
    """Without this, a crash near the end of a long job threw away every earlier result."""
    saves: list[str] = []
    companies = [company("First"), company("Second")]

    async def enrich(item: Company) -> FakeOutcome:
        saves.append(f"enriched {item.display_name}")
        return FakeOutcome(True, "ok")

    async def commit() -> None:
        saves.append("saved")

    await run_batch("check_domain_age", companies, enrich, after_each=commit)

    assert saves == ["enriched First", "saved", "enriched Second", "saved"]


async def test_each_outcome_is_recorded_before_it_is_saved() -> None:
    """The record is what lets the next run start with companies not yet tried."""
    events: list[str] = []
    companies = [company("Found Co"), company("Nothing Co")]

    async def enrich(item: Company) -> FakeOutcome:
        return FakeOutcome(item.display_name == "Found Co", f"checked {item.display_name}")

    async def record(item: Company, outcome: Outcome) -> None:
        events.append(f"recorded {item.display_name}: {outcome.succeeded}, {outcome.message}")

    async def commit() -> None:
        events.append("saved")

    await run_batch("check_domain_age", companies, enrich, record=record, after_each=commit)

    assert events == [
        "recorded Found Co: True, checked Found Co",
        "saved",
        "recorded Nothing Co: False, checked Nothing Co",
        "saved",
    ]
