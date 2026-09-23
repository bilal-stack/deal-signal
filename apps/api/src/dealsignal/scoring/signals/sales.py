"""Signals for finding companies to sell to.

These read the same facts the acquisition signals read, and several reward the
opposite direction. A website nobody has touched since 2019 suggests an owner who
may sell; it also suggests a company that is not buying anything new. A business
opening new locations is a poor acquisition target and an excellent prospect.
"""

from __future__ import annotations

from dealsignal.scoring.base import Signal, SignalResult
from dealsignal.scoring.context import ScoringContext
from dealsignal.scoring.signals.momentum import MINIMUM_REVIEWS_FOR_A_TREND

GROWING_FAST = 1.2
GROWING = 1.0

RECENTLY_UPDATED_YEARS = 1
STILL_CURRENT_YEARS = 2

MANY_LOCATIONS = 3
SEVERAL_LOCATIONS = 2


class BusinessCustomersSignal(Signal):
    """A company that sells to businesses is used to buying from them."""

    key = "business_customers"
    max_points = 15

    def evaluate(self, context: ScoringContext) -> SignalResult | None:
        sells_to_businesses = context.facts.sells_to_businesses
        if sells_to_businesses is None:
            return None
        if not sells_to_businesses:
            return self.award(0, "Serves consumers rather than businesses")
        return self.award(
            self.max_points,
            "Serves business customers",
            evidence=context.facts.evidence.get("sells_to_businesses"),
        )


class GrowingReviewsSignal(Signal):
    """Rising review volume means more customers, and usually more spending."""

    key = "growing_reviews"
    max_points = 15

    def evaluate(self, context: ScoringContext) -> SignalResult | None:
        ratio = context.facts.review_growth_ratio
        reviews = context.facts.review_count
        if ratio is None or reviews is None or reviews < MINIMUM_REVIEWS_FOR_A_TREND:
            return None

        change = round((ratio - 1) * 100)
        if ratio >= GROWING_FAST:
            return self.award(self.max_points, f"New reviews up {change}% year on year")
        if ratio >= GROWING:
            return self.award(self.max_points * 0.5, "Review growth is steady")
        return self.award(0, f"New reviews down {abs(change)}% year on year")


class ActiveWebsiteSignal(Signal):
    """A recently updated site belongs to a business that is still investing."""

    key = "active_website"
    max_points = 10

    def evaluate(self, context: ScoringContext) -> SignalResult | None:
        updated = context.facts.website_last_updated_year
        if updated is None:
            return None

        age = context.current_year - updated
        if age <= RECENTLY_UPDATED_YEARS:
            return self.award(self.max_points, "Website updated within the last year")
        if age <= STILL_CURRENT_YEARS:
            return self.award(self.max_points * 0.5, f"Website last updated in {updated}")
        return self.award(0, f"Website not updated since {updated}")


class MultipleLocationsSignal(Signal):
    """More sites usually means more budget and more seats to sell into."""

    key = "multiple_locations"
    max_points = 10

    def evaluate(self, context: ScoringContext) -> SignalResult | None:
        locations = context.facts.location_count
        if locations is None:
            return None
        if locations >= MANY_LOCATIONS:
            return self.award(self.max_points, f"Operates from {locations} locations")
        if locations >= SEVERAL_LOCATIONS:
            return self.award(self.max_points * 0.5, f"Operates from {locations} locations")
        return self.award(0, "Operates from a single location")


class NamedContactSignal(Signal):
    """A lead with a named decision-maker can actually be contacted."""

    key = "named_contact"
    max_points = 15

    def evaluate(self, context: ScoringContext) -> SignalResult | None:
        if context.facts.has_named_contact is None:
            return None
        if not context.facts.has_named_contact:
            return self.award(0, "No named decision-maker on record")
        return self.award(self.max_points, "A named decision-maker is on record")
