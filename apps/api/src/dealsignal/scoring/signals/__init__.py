"""The signal sets, one per Buy Box mode.

Adding a signal means writing the class and listing it in a set. Nothing else in
the codebase changes. Each set adds up to 100 points, which keeps a Buy Box weight
override easy to reason about.
"""

from collections.abc import Mapping

from dealsignal.models.enums import BuyBoxMode
from dealsignal.scoring.base import Signal
from dealsignal.scoring.signals.fit import (
    EmployeeFitSignal,
    RecurringRevenueSignal,
    RevenueFitSignal,
)
from dealsignal.scoring.signals.momentum import ReviewMomentumSignal, WebsiteFreshnessSignal
from dealsignal.scoring.signals.ownership import (
    FamilyOwnershipSignal,
    IndependenceSignal,
    SingleLocationSignal,
)
from dealsignal.scoring.signals.sales import (
    ActiveWebsiteSignal,
    BusinessCustomersSignal,
    GrowingReviewsSignal,
    MultipleLocationsSignal,
    NamedContactSignal,
)
from dealsignal.scoring.signals.tenure import OwnerAgeSignal, YearsInBusinessSignal

ACQUISITION_SIGNALS: tuple[Signal, ...] = (
    RevenueFitSignal(),  # 15   does it match the Buy Box
    EmployeeFitSignal(),  # 10
    RecurringRevenueSignal(),  # 15
    YearsInBusinessSignal(),  # 15   is the owner likely to sell
    OwnerAgeSignal(),  # 15
    IndependenceSignal(),  # 10
    WebsiteFreshnessSignal(max_points=10),  # 10   a stale site is a good sign here
    FamilyOwnershipSignal(),  #  5
    SingleLocationSignal(),  #  5
)

SALES_SIGNALS: tuple[Signal, ...] = (
    RevenueFitSignal(max_points=20),  # 20   can they afford it
    EmployeeFitSignal(max_points=15),  # 15
    BusinessCustomersSignal(max_points=20),  # 20   used to buying from businesses
    NamedContactSignal(max_points=20),  # 20   someone to actually call
    ActiveWebsiteSignal(max_points=15),  # 15   the opposite of the acquisition reading
    MultipleLocationsSignal(),  # 10   so is this
)

REVIEW_SIGNALS: tuple[Signal, ...] = (ReviewMomentumSignal(), GrowingReviewsSignal())
"""Written and tested, but not in either set: nothing supplies review counts yet.

Overture publishes none, and the Google Places source that would is off by default
because it needs a billing account. A signal that can never fire is not harmless:
it counts towards the total, so every company loses confidence for a question we
were never able to ask. Add these back with the source that answers them."""

SIGNAL_SETS: Mapping[BuyBoxMode, tuple[Signal, ...]] = {
    BuyBoxMode.ACQUISITION: ACQUISITION_SIGNALS,
    BuyBoxMode.SALES: SALES_SIGNALS,
}

DEFAULT_SIGNALS = ACQUISITION_SIGNALS
"""Kept for callers that predate modes."""

TOTAL_POINTS = sum(signal.max_points for signal in DEFAULT_SIGNALS)


def signals_for(mode: BuyBoxMode | str) -> tuple[Signal, ...]:
    """The signal set for a Buy Box mode."""
    return SIGNAL_SETS[BuyBoxMode(mode)]


__all__ = [
    "ACQUISITION_SIGNALS",
    "DEFAULT_SIGNALS",
    "REVIEW_SIGNALS",
    "SALES_SIGNALS",
    "SIGNAL_SETS",
    "TOTAL_POINTS",
    "ActiveWebsiteSignal",
    "BusinessCustomersSignal",
    "EmployeeFitSignal",
    "FamilyOwnershipSignal",
    "GrowingReviewsSignal",
    "IndependenceSignal",
    "MultipleLocationsSignal",
    "NamedContactSignal",
    "OwnerAgeSignal",
    "RecurringRevenueSignal",
    "RevenueFitSignal",
    "ReviewMomentumSignal",
    "SingleLocationSignal",
    "WebsiteFreshnessSignal",
    "YearsInBusinessSignal",
    "signals_for",
]
