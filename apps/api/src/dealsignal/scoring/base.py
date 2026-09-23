"""The signal contract.

A signal looks at the facts and either awards points with a reason, or abstains
because the data is not there. Abstaining is not a zero: it removes the signal from
the total, which lowers confidence instead of the score.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from pydantic import BaseModel, ConfigDict, Field

from dealsignal.scoring.context import ScoringContext


class SignalResult(BaseModel):
    """Points awarded by one signal, with the sentence the user will read."""

    model_config = ConfigDict(frozen=True)

    key: str
    points: float = Field(ge=0)
    max_points: int = Field(gt=0)
    reason: str
    evidence: str | None = None


class Signal(ABC):
    """One reason a company might be a good acquisition target.

    Subclasses set `key` and `max_points` and implement `evaluate`. Adding a signal
    means adding a class and listing it in `scoring.signals.DEFAULT_SIGNALS`; the
    scorer itself never changes.
    """

    key: str
    max_points: int

    def __init__(self, max_points: int | None = None) -> None:
        """Optionally re-weight this signal for a particular signal set.

        Revenue fit matters in both modes but not equally, so the weight belongs to
        the set that uses the signal, not only to the class.
        """
        if max_points is not None:
            if max_points <= 0:
                raise ValueError("A signal must be worth at least one point.")
            self.max_points = max_points

    def __init_subclass__(cls, **kwargs: object) -> None:
        super().__init_subclass__(**kwargs)
        if ABC in cls.__bases__:
            return
        for attribute in ("key", "max_points"):
            if not getattr(cls, attribute, None):
                raise TypeError(f"{cls.__name__} must define {attribute}.")

    @abstractmethod
    def evaluate(self, context: ScoringContext) -> SignalResult | None:
        """Award points, or return None when the facts needed are unknown."""

    def award(self, points: float, reason: str, *, evidence: str | None = None) -> SignalResult:
        """Build a result, clamped to this signal's maximum."""
        return SignalResult(
            key=self.key,
            points=min(max(points, 0.0), float(self.max_points)),
            max_points=self.max_points,
            reason=reason,
            evidence=evidence,
        )

    @staticmethod
    def proportion_within(value: float, low: float, high: float) -> float:
        """1.0 inside the range, tapering to 0.0 one range-width outside it.

        Used by the range signals, so a company just outside the Buy Box still ranks
        above one that misses by a mile.
        """
        if low <= value <= high:
            return 1.0
        span = max(high - low, 1.0)
        distance = low - value if value < low else value - high
        return max(0.0, 1.0 - distance / span)
