"""Signals about who owns the company and how it is run."""

from __future__ import annotations

from dealsignal.scoring.base import Signal, SignalResult
from dealsignal.scoring.context import ScoringContext

SINGLE_LOCATION = 1


class IndependenceSignal(Signal):
    """A company already owned by a group or a fund is rarely available."""

    key = "independence"
    max_points = 10

    def evaluate(self, context: ScoringContext) -> SignalResult | None:
        facts = context.facts
        if facts.has_parent_company is None and facts.is_private_equity_owned is None:
            return None

        if facts.is_private_equity_owned:
            return self.award(0, "Already owned by a private equity firm")
        if facts.has_parent_company:
            return self.award(0, "Part of a larger group")

        return self.award(
            self.max_points,
            "Independent, with no parent company on record",
            evidence=facts.evidence.get("has_parent_company"),
        )


class FamilyOwnershipSignal(Signal):
    """Family firms without a named successor are classic succession sales."""

    key = "family_ownership"
    max_points = 5

    def evaluate(self, context: ScoringContext) -> SignalResult | None:
        mentions_family = context.facts.mentions_family_ownership
        if mentions_family is None:
            return None
        if not mentions_family:
            return self.award(0, "No mention of family ownership")

        return self.award(
            self.max_points,
            "Describes itself as family-owned",
            evidence=context.facts.evidence.get("mentions_family_ownership"),
        )


class SingleLocationSignal(Signal):
    """One site usually means one owner, one decision, and a simpler deal."""

    key = "single_location"
    max_points = 5

    def evaluate(self, context: ScoringContext) -> SignalResult | None:
        locations = context.facts.location_count
        if locations is None:
            return None
        if locations == SINGLE_LOCATION:
            return self.award(self.max_points, "Operates from a single location")
        return self.award(0, f"Operates from {locations} locations")
