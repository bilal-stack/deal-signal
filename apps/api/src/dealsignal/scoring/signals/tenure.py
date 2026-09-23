"""Signals about how long the business and its owner have been in place."""

from __future__ import annotations

from dealsignal.scoring.base import Signal, SignalResult
from dealsignal.scoring.context import ScoringContext

LONG_ESTABLISHED_YEARS = 25
ESTABLISHED_YEARS = 15
YOUNG_YEARS = 10

RETIREMENT_AGE = 65
NEAR_RETIREMENT_AGE = 60
MID_CAREER_AGE = 55
EARLY_CAREER_AGE = 50


class YearsInBusinessSignal(Signal):
    """An older business is more likely to have a founder ready to step back.

    It also tends to have real customers and records, which matters to a buyer.
    """

    key = "years_in_business"
    max_points = 15

    def evaluate(self, context: ScoringContext) -> SignalResult | None:
        founded = context.facts.founded_year
        if founded is not None:
            years = context.current_year - founded
            return self.award(
                self.max_points * self._share(years),
                f"Founded {founded} ({years} years in business)",
                evidence=context.facts.evidence.get("founded_year"),
            )
        return self._from_domain_age(context)

    def _from_domain_age(self, context: ScoringContext) -> SignalResult | None:
        """Use the website domain's age as a lower bound on the business's age.

        A domain registered in 2005 shows the business has been trading at least
        that long. A recently registered domain shows nothing, because domains are
        re-registered all the time, so it abstains rather than calling an old
        business young.
        """
        registered = context.facts.domain_registered_year
        if registered is None:
            return None

        years = context.current_year - registered
        if years < YOUNG_YEARS:
            return None

        return self.award(
            self.max_points * self._share(years),
            f"Website domain registered in {registered}, so trading at least {years} years",
            evidence=context.facts.evidence.get("domain_registered_year"),
        )

    @staticmethod
    def _share(years: int) -> float:
        if years >= LONG_ESTABLISHED_YEARS:
            return 1.0
        if years >= ESTABLISHED_YEARS:
            return 0.7
        if years >= YOUNG_YEARS:
            return 0.4
        return 0.1


class OwnerAgeSignal(Signal):
    """Retirement is the most common reason a small business comes up for sale.

    Only the birth year is ever stored, and only where a public registry publishes
    it (UK and France). Elsewhere this signal abstains, which costs confidence, not
    points.
    """

    key = "owner_age"
    max_points = 15

    def evaluate(self, context: ScoringContext) -> SignalResult | None:
        birth_year = context.facts.owner_birth_year
        if birth_year is None:
            return None

        age = context.current_year - birth_year
        if age >= RETIREMENT_AGE:
            share = 1.0
        elif age >= NEAR_RETIREMENT_AGE:
            share = 0.85
        elif age >= MID_CAREER_AGE:
            share = 0.6
        elif age >= EARLY_CAREER_AGE:
            share = 0.35
        else:
            share = 0.1

        return self.award(
            self.max_points * share,
            f"Owner born {birth_year}, around {age} years old",
            evidence=context.facts.evidence.get("owner_birth_year"),
        )
