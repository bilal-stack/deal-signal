"""Signals that suggest an owner is winding down rather than pushing forward."""

from __future__ import annotations

from dealsignal.scoring.base import Signal, SignalResult
from dealsignal.scoring.context import ScoringContext

VERY_STALE_YEARS = 5
STALE_YEARS = 2

SHARPLY_SLOWING = 0.5
SLOWING = 0.8
MINIMUM_REVIEWS_FOR_A_TREND = 10


class WebsiteFreshnessSignal(Signal):
    """A site left untouched for years often means an owner who has stopped investing."""

    key = "website_freshness"
    max_points = 5

    def evaluate(self, context: ScoringContext) -> SignalResult | None:
        updated = context.facts.website_last_updated_year
        if updated is None:
            return None

        age = context.current_year - updated
        if age >= VERY_STALE_YEARS:
            return self.award(self.max_points, f"Website not updated since {updated}")
        if age >= STALE_YEARS:
            return self.award(self.max_points * 0.5, f"Website last updated in {updated}")
        return self.award(0, "Website is actively maintained")


class ReviewMomentumSignal(Signal):
    """Slowing review growth is an early sign of a business coasting."""

    key = "review_momentum"
    max_points = 5

    def evaluate(self, context: ScoringContext) -> SignalResult | None:
        ratio = context.facts.review_growth_ratio
        reviews = context.facts.review_count
        if ratio is None or reviews is None or reviews < MINIMUM_REVIEWS_FOR_A_TREND:
            return None

        drop_percent = round((1 - ratio) * 100)
        if ratio <= SHARPLY_SLOWING:
            return self.award(self.max_points, f"New reviews down {drop_percent}% year on year")
        if ratio <= SLOWING:
            return self.award(
                self.max_points * 0.5, f"New reviews down {drop_percent}% year on year"
            )
        return self.award(0, "Review growth is steady or rising")
