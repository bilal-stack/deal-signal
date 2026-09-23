from __future__ import annotations

import pytest

from dealsignal.scoring.base import Signal, SignalResult
from dealsignal.scoring.context import ScoringContext


def test_a_signal_must_declare_a_key_and_a_maximum() -> None:
    with pytest.raises(TypeError, match="must define"):

        class Nameless(Signal):
            max_points = 5

            def evaluate(self, context: ScoringContext) -> SignalResult | None:
                return None


def test_award_never_exceeds_the_maximum() -> None:
    class Generous(Signal):
        key = "generous"
        max_points = 5

        def evaluate(self, context: ScoringContext) -> SignalResult:
            return self.award(999, "Too many points")

    result = Generous().award(999, "x")

    assert result.points == 5


def test_proportion_within_tapers_outside_the_range() -> None:
    assert Signal.proportion_within(5, 1, 10) == 1.0
    assert Signal.proportion_within(11, 1, 10) == pytest.approx(0.889, abs=0.01)
    assert Signal.proportion_within(100, 1, 10) == 0.0


class RecordingEvidence(dict[str, str]):
    """Remembers every evidence key a signal asks for."""

    def __init__(self) -> None:
        super().__init__()
        self.asked: set[str] = set()

    def get(self, key: str, default: str | None = None) -> str | None:  # type: ignore[override]
        self.asked.add(key)
        return super().get(key, default)


def test_every_evidence_key_a_signal_reads_is_one_scoring_supplies() -> None:
    """A signal can only quote evidence that scoring files under the same name."""
    from dealsignal.scoring.context import BuyBoxCriteria, CompanyFacts
    from dealsignal.scoring.signals import ACQUISITION_SIGNALS, SALES_SIGNALS
    from dealsignal.services.facts import OWNER_BIRTH_YEAR
    from dealsignal.services.scoring_service import (
        EVIDENCE_FOR_ROW_FACTS,
        STORED_FACT_TO_SCORING_FACT,
    )

    supplied = {
        *STORED_FACT_TO_SCORING_FACT.values(),
        *EVIDENCE_FOR_ROW_FACTS.values(),
        OWNER_BIRTH_YEAR,
    }
    evidence = RecordingEvidence()
    facts = CompanyFacts.model_construct(
        name="Evidence Co",
        country="US",
        founded_year=1990,
        employee_count=20,
        revenue_low=2_000_000,
        revenue_high=4_000_000,
        owner_birth_year=1955,
        has_recurring_revenue=True,
        sells_to_businesses=True,
        mentions_family_ownership=True,
        has_parent_company=False,
        is_private_equity_owned=False,
        domain_registered_year=2001,
        website_last_updated_year=2019,
        location_count=1,
        has_named_contact=True,
        evidence=evidence,
    )
    criteria = BuyBoxCriteria(
        revenue_min=1_000_000, revenue_max=10_000_000, employees_min=5, employees_max=50
    )
    context = ScoringContext(facts=facts, criteria=criteria)

    for signal in (*ACQUISITION_SIGNALS, *SALES_SIGNALS):
        signal.evaluate(context)

    assert {"has_recurring_revenue", "mentions_family_ownership", "has_parent_company"} <= (
        evidence.asked
    ), "the test must reach the signals that quote the website"
    assert evidence.asked <= supplied, f"never supplied: {sorted(evidence.asked - supplied)}"
