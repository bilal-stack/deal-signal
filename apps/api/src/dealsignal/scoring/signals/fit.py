"""Signals that measure how closely a company matches the Buy Box."""

from __future__ import annotations

from dealsignal.scoring.base import Signal, SignalResult
from dealsignal.scoring.context import ScoringContext

MILLION = 1_000_000


def _format_money(amount: float) -> str:
    """2500000 -> '$2.5M'. Ranges read better than raw digits in a reason."""
    millions = amount / MILLION
    return f"${millions:.1f}M" if millions < 10 else f"${millions:.0f}M"


class RevenueFitSignal(Signal):
    """Revenue inside the Buy Box range, tapering off outside it."""

    key = "revenue_fit"
    max_points = 15

    def evaluate(self, context: ScoringContext) -> SignalResult | None:
        facts, criteria = context.facts, context.criteria
        if facts.revenue_low is None or facts.revenue_high is None:
            return None
        if criteria.revenue_min is None and criteria.revenue_max is None:
            return None

        midpoint = (facts.revenue_low + facts.revenue_high) / 2
        low = float(criteria.revenue_min or 0)
        high = float(criteria.revenue_max or midpoint)
        share = self.proportion_within(midpoint, low, high)

        estimate = f"{_format_money(facts.revenue_low)}-{_format_money(facts.revenue_high)}"
        verdict = "inside your range" if share == 1.0 else "outside your range"
        return self.award(
            self.max_points * share,
            f"Estimated revenue {estimate}, {verdict}",
            evidence=facts.evidence.get("revenue"),
        )


class EmployeeFitSignal(Signal):
    """Headcount inside the Buy Box range."""

    key = "employee_fit"
    max_points = 10

    def evaluate(self, context: ScoringContext) -> SignalResult | None:
        facts, criteria = context.facts, context.criteria
        if facts.employee_count is None:
            return None
        if criteria.employees_min is None and criteria.employees_max is None:
            return None

        low = float(criteria.employees_min or 0)
        high = float(criteria.employees_max or facts.employee_count)
        share = self.proportion_within(float(facts.employee_count), low, high)

        verdict = "inside your range" if share == 1.0 else "outside your range"
        return self.award(
            self.max_points * share,
            f"About {facts.employee_count} employees, {verdict}",
            evidence=facts.evidence.get("employee_count"),
        )


class RecurringRevenueSignal(Signal):
    """Repeat revenue and business customers make a company easier to own."""

    key = "recurring_revenue"
    max_points = 15

    def evaluate(self, context: ScoringContext) -> SignalResult | None:
        facts = context.facts
        if facts.has_recurring_revenue is None and facts.sells_to_businesses is None:
            return None

        points = 0.0
        parts: list[str] = []
        if facts.has_recurring_revenue:
            points += self.max_points * 0.7
            parts.append("sells contracts or subscriptions")
        if facts.sells_to_businesses:
            points += self.max_points * 0.3
            parts.append("sells to other businesses")

        reason = ", ".join(parts).capitalize() if parts else "No sign of repeat revenue"
        evidence = facts.evidence.get("has_recurring_revenue") or facts.evidence.get(
            "sells_to_businesses"
        )
        return self.award(points, reason, evidence=evidence)
