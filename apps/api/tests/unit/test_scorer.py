"""The rule that matters most: missing data lowers confidence, never the score."""

from __future__ import annotations

from datetime import date

import pytest

from dealsignal.scoring.base import Signal, SignalResult
from dealsignal.scoring.context import BuyBoxCriteria, CompanyFacts, ScoringContext
from dealsignal.scoring.scorer import Scorer

TODAY = date(2026, 9, 16)


class AlwaysFullMarks(Signal):
    key = "always_full"
    max_points = 10

    def evaluate(self, context: ScoringContext) -> SignalResult:
        return self.award(self.max_points, "Full marks")


class AlwaysZero(Signal):
    key = "always_zero"
    max_points = 10

    def evaluate(self, context: ScoringContext) -> SignalResult:
        return self.award(0, "No points")


class AlwaysAbstains(Signal):
    key = "no_data"
    max_points = 30

    def evaluate(self, context: ScoringContext) -> SignalResult | None:
        return None


def context(weights: dict[str, int] | None = None) -> ScoringContext:
    return ScoringContext(
        facts=CompanyFacts(name="Test Co", country="US"),
        criteria=BuyBoxCriteria(weights=weights or {}),
        today=TODAY,
    )


def test_a_scorer_needs_at_least_one_signal() -> None:
    with pytest.raises(ValueError, match="at least one signal"):
        Scorer([])


def test_full_marks_everywhere_is_one_hundred() -> None:
    result = Scorer([AlwaysFullMarks()]).score(context())

    assert result.score == 100
    assert result.confidence == 1.0
    assert result.confidence_label == "high"


def test_missing_data_lowers_confidence_but_not_the_score() -> None:
    result = Scorer([AlwaysFullMarks(), AlwaysAbstains()]).score(context())

    assert result.score == 100, "an unknown fact must not cost points"
    assert result.confidence == pytest.approx(0.25), "10 of 40 possible points were known"
    assert result.missing_signals == ["no_data"]
    assert result.confidence_label == "low"


def test_score_is_the_share_of_the_points_we_could_judge() -> None:
    result = Scorer([AlwaysFullMarks(), AlwaysZero()]).score(context())

    assert result.score == 50
    assert result.confidence == 1.0


def test_a_company_we_know_nothing_about_has_no_score_rather_than_zero() -> None:
    """Zero means "we judged it and it does not fit". Unknown must stay unknown,
    or an unenriched company looks like a bad one."""
    result = Scorer([AlwaysAbstains()]).score(context())

    assert result.score is None
    assert result.score is None
    assert result.confidence == 0
    assert result.missing_signals == ["no_data"]


def test_a_company_that_earns_no_points_still_scores_zero() -> None:
    result = Scorer([AlwaysZero()]).score(context())

    assert result.score == 0, "we had the data and it did not fit"
    assert result.score is not None


def test_reasons_come_back_strongest_first() -> None:
    result = Scorer([AlwaysZero(), AlwaysFullMarks()]).score(context())

    assert [reason.key for reason in result.reasons] == ["always_full", "always_zero"]


def test_a_buy_box_can_switch_a_signal_off() -> None:
    result = Scorer([AlwaysFullMarks(), AlwaysZero()]).score(context({"always_zero": 0}))

    assert result.score == 100
    assert [reason.key for reason in result.reasons] == ["always_full"]


def test_a_buy_box_can_re_weight_a_signal() -> None:
    result = Scorer([AlwaysFullMarks(), AlwaysZero()]).score(context({"always_full": 30}))

    assert result.score == 75, "30 of 40 points earned once the weight is raised"


def test_every_score_arrives_with_its_reasons() -> None:
    result = Scorer([AlwaysFullMarks()]).score(context())

    assert result.reasons
    assert all(reason.reason for reason in result.reasons)


def test_the_score_reports_how_many_signals_were_in_play() -> None:
    """So the UI can say "1 of 2 unknown" instead of assuming a fixed number."""
    result = Scorer([AlwaysFullMarks(), AlwaysAbstains()]).score(context())

    assert result.total_signals == 2


def test_a_switched_off_signal_is_not_counted_as_in_play() -> None:
    result = Scorer([AlwaysFullMarks(), AlwaysZero()]).score(context({"always_zero": 0}))

    assert result.total_signals == 1
