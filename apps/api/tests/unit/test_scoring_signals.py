"""Each signal is a pure function of the facts, so every case is a two-line fixture."""

from __future__ import annotations

from datetime import date

import pytest

from dealsignal.scoring.base import Signal
from dealsignal.scoring.context import BuyBoxCriteria, CompanyFacts, ScoringContext
from dealsignal.scoring.signals import DEFAULT_SIGNALS, TOTAL_POINTS
from dealsignal.scoring.signals.fit import EmployeeFitSignal, RevenueFitSignal
from dealsignal.scoring.signals.momentum import ReviewMomentumSignal, WebsiteFreshnessSignal
from dealsignal.scoring.signals.ownership import IndependenceSignal, SingleLocationSignal
from dealsignal.scoring.signals.tenure import OwnerAgeSignal, YearsInBusinessSignal

TODAY = date(2026, 9, 16)


def context(**facts: object) -> ScoringContext:
    """A context with only the facts a test cares about; everything else unknown."""
    defaults = {"name": "Test Co", "country": "US"}
    return ScoringContext(
        facts=CompanyFacts(**{**defaults, **facts}),
        criteria=BuyBoxCriteria(
            revenue_min=2_000_000, revenue_max=10_000_000, employees_min=5, employees_max=50
        ),
        today=TODAY,
    )


def test_signal_points_add_up_to_one_hundred() -> None:
    assert TOTAL_POINTS == 100


@pytest.mark.parametrize("signal", DEFAULT_SIGNALS, ids=lambda s: s.key)
def test_every_signal_abstains_when_it_knows_nothing(signal: Signal) -> None:
    assert signal.evaluate(context()) is None


def test_a_long_established_business_earns_full_marks() -> None:
    result = YearsInBusinessSignal().evaluate(context(founded_year=1996))

    assert result is not None
    assert result.points == result.max_points
    assert "1996" in result.reason
    assert "30 years" in result.reason


def test_a_new_business_earns_almost_nothing() -> None:
    result = YearsInBusinessSignal().evaluate(context(founded_year=2024))

    assert result is not None
    assert result.points < result.max_points * 0.2


def test_an_owner_near_retirement_earns_full_marks() -> None:
    result = OwnerAgeSignal().evaluate(context(owner_birth_year=1958))

    assert result is not None
    assert result.points == result.max_points
    assert "1958" in result.reason


def test_a_young_owner_earns_little() -> None:
    result = OwnerAgeSignal().evaluate(context(owner_birth_year=1992))

    assert result is not None
    assert result.points < result.max_points * 0.2


def test_revenue_inside_the_range_earns_full_marks() -> None:
    result = RevenueFitSignal().evaluate(context(revenue_low=3_000_000, revenue_high=5_000_000))

    assert result is not None
    assert result.points == result.max_points
    assert "inside your range" in result.reason


def test_revenue_far_outside_the_range_earns_nothing() -> None:
    result = RevenueFitSignal().evaluate(context(revenue_low=80_000_000, revenue_high=90_000_000))

    assert result is not None
    assert result.points == 0
    assert "outside your range" in result.reason


def test_headcount_just_outside_the_range_still_scores_something() -> None:
    result = EmployeeFitSignal().evaluate(context(employee_count=60))

    assert result is not None
    assert 0 < result.points < result.max_points


def test_a_private_equity_owned_company_earns_nothing_for_independence() -> None:
    result = IndependenceSignal().evaluate(
        context(is_private_equity_owned=True, has_parent_company=True)
    )

    assert result is not None
    assert result.points == 0
    assert "private equity" in result.reason


def test_an_independent_company_earns_full_marks() -> None:
    result = IndependenceSignal().evaluate(
        context(is_private_equity_owned=False, has_parent_company=False)
    )

    assert result is not None
    assert result.points == result.max_points


def test_a_stale_website_is_a_signal_not_a_penalty() -> None:
    result = WebsiteFreshnessSignal().evaluate(context(website_last_updated_year=2019))

    assert result is not None
    assert result.points == result.max_points
    assert "2019" in result.reason


def test_review_momentum_needs_enough_reviews_to_mean_anything() -> None:
    assert ReviewMomentumSignal().evaluate(context(review_count=3, review_growth_ratio=0.2)) is None


def test_sharply_slowing_reviews_earn_full_marks() -> None:
    result = ReviewMomentumSignal().evaluate(context(review_count=120, review_growth_ratio=0.4))

    assert result is not None
    assert result.points == result.max_points
    assert "60%" in result.reason


def test_a_single_location_earns_full_marks() -> None:
    result = SingleLocationSignal().evaluate(context(location_count=1))

    assert result is not None
    assert result.points == result.max_points


def test_evidence_is_passed_through_to_the_reason() -> None:
    result = YearsInBusinessSignal().evaluate(
        context(founded_year=1996, evidence={"founded_year": "Serving Dallas since 1996"})
    )

    assert result is not None
    assert result.evidence == "Serving Dallas since 1996"
