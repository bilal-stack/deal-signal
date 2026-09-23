"""The same company, read two ways.

The point of modes is that several signals invert. These tests pin that down with
identical facts scored under each set, so a change that quietly makes the two
modes agree fails loudly.
"""

from __future__ import annotations

from datetime import date

import pytest

from dealsignal.models.enums import BuyBoxMode
from dealsignal.scoring.context import BuyBoxCriteria, CompanyFacts, ScoringContext
from dealsignal.scoring.scorer import Scorer
from dealsignal.scoring.signals import ACQUISITION_SIGNALS, SALES_SIGNALS, signals_for
from dealsignal.scoring.signals.fit import RevenueFitSignal
from dealsignal.scoring.signals.momentum import ReviewMomentumSignal
from dealsignal.scoring.signals.sales import (
    ActiveWebsiteSignal,
    GrowingReviewsSignal,
    MultipleLocationsSignal,
    NamedContactSignal,
)

TODAY = date(2026, 9, 17)


def context(**facts: object) -> ScoringContext:
    return ScoringContext(
        facts=CompanyFacts(name="Test Co", country="US", **facts),
        criteria=BuyBoxCriteria(),
        today=TODAY,
    )


@pytest.mark.parametrize(
    "signals", [ACQUISITION_SIGNALS, SALES_SIGNALS], ids=["acquisition", "sales"]
)
def test_each_set_adds_up_to_one_hundred(signals: tuple[object, ...]) -> None:
    assert sum(signal.max_points for signal in signals) == 100  # type: ignore[attr-defined]


@pytest.mark.parametrize(
    "signals", [ACQUISITION_SIGNALS, SALES_SIGNALS], ids=["acquisition", "sales"]
)
def test_signal_keys_are_unique_within_a_set(signals: tuple[object, ...]) -> None:
    keys = [signal.key for signal in signals]  # type: ignore[attr-defined]
    assert len(keys) == len(set(keys))


def test_the_mode_picks_its_own_set() -> None:
    assert signals_for(BuyBoxMode.ACQUISITION) is ACQUISITION_SIGNALS
    assert signals_for("sales") is SALES_SIGNALS


def test_a_stale_website_helps_an_acquisition_and_hurts_a_sale() -> None:
    stale = context(website_last_updated_year=2018)

    acquisition = Scorer(ACQUISITION_SIGNALS).score(stale)
    sales = Scorer(SALES_SIGNALS).score(stale)

    assert acquisition.score == 100, "an untouched site suggests an owner winding down"
    assert sales.score == 0, "and a company that is not buying anything new"


def test_review_signals_read_growth_in_opposite_directions() -> None:
    """Neither set uses these yet, because nothing supplies review counts. The
    inversion is kept under test so it is right when a source does."""
    growing = context(review_count=200, review_growth_ratio=1.5)

    assert Scorer([GrowingReviewsSignal()]).score(growing).score == 100
    assert Scorer([ReviewMomentumSignal()]).score(growing).score == 0


def test_no_scored_signal_depends_on_review_data() -> None:
    """A signal nothing can answer still lowers confidence for every company."""
    for signals in (ACQUISITION_SIGNALS, SALES_SIGNALS):
        keys = {signal.key for signal in signals}
        assert "review_momentum" not in keys
        assert "growing_reviews" not in keys


def test_more_locations_help_a_sale_and_not_an_acquisition() -> None:
    expanding = context(location_count=4)

    assert Scorer(SALES_SIGNALS).score(expanding).score == 100
    assert Scorer(ACQUISITION_SIGNALS).score(expanding).score == 0


def test_owner_age_means_nothing_to_a_salesperson() -> None:
    retiring = context(owner_birth_year=1950)

    acquisition = Scorer(ACQUISITION_SIGNALS).score(retiring)
    sales = Scorer(SALES_SIGNALS).score(retiring)

    assert acquisition.score == 100
    assert sales.score is None, "no sales signal reads owner age, so nothing is judged"


def test_a_reweighted_signal_keeps_its_own_weight_per_set() -> None:
    """Sharing one class must not leak a weight from one set into the other."""
    acquisition_revenue = next(s for s in ACQUISITION_SIGNALS if isinstance(s, RevenueFitSignal))
    sales_revenue = next(s for s in SALES_SIGNALS if isinstance(s, RevenueFitSignal))

    assert acquisition_revenue.max_points == 15
    assert sales_revenue.max_points == 20
    assert RevenueFitSignal.max_points == 15, "the class default is untouched"


def test_a_signal_cannot_be_weighted_at_zero() -> None:
    with pytest.raises(ValueError, match="at least one point"):
        RevenueFitSignal(max_points=0)


def test_an_unknown_contact_is_not_the_same_as_no_contact() -> None:
    assert NamedContactSignal().evaluate(context()) is None
    result = NamedContactSignal().evaluate(context(has_named_contact=True))
    assert result is not None
    assert result.points == result.max_points


@pytest.mark.parametrize(
    "signal", [GrowingReviewsSignal(), ActiveWebsiteSignal(), MultipleLocationsSignal()]
)
def test_sales_signals_abstain_without_data(signal: object) -> None:
    assert signal.evaluate(context()) is None  # type: ignore[attr-defined]
