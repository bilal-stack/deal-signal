"""Turning signals into a score.

    score      = 100 x points earned / points available from signals that had data
    confidence = points available from those signals / points of every signal

Missing data therefore lowers confidence and never the score, which is what stops a
thin record from looking like a bad company.
"""

from __future__ import annotations

from collections.abc import Sequence

from pydantic import BaseModel, ConfigDict, Field

from dealsignal.core.logging import get_logger
from dealsignal.scoring.base import Signal, SignalResult
from dealsignal.scoring.context import ScoringContext

log = get_logger(__name__)

MAX_SCORE = 100.0
HIGH_CONFIDENCE = 0.75
MEDIUM_CONFIDENCE = 0.4


class ScoreResult(BaseModel):
    """A score that always arrives with its reasons.

    `score` is None when no signal had anything to work with. That is different
    from zero: zero means "we looked and it does not fit", None means "we cannot
    say yet". Showing 0 for an unenriched company would be the same lie as showing
    a confident revenue estimate for one.
    """

    model_config = ConfigDict(frozen=True)

    score: float | None = Field(default=None, ge=0, le=MAX_SCORE)
    confidence: float = Field(ge=0, le=1)
    reasons: list[SignalResult]
    missing_signals: list[str]
    total_signals: int = Field(default=0, ge=0)
    """How many signals were in play, so "3 unknown" can say "3 of 7"."""

    @property
    def confidence_label(self) -> str:
        if self.confidence >= HIGH_CONFIDENCE:
            return "high"
        if self.confidence >= MEDIUM_CONFIDENCE:
            return "medium"
        return "low"


class Scorer:
    """Runs every signal over one company.

    Signals are injected, so a test can score with a single signal and the set can
    grow without this class changing.
    """

    def __init__(self, signals: Sequence[Signal]) -> None:
        if not signals:
            raise ValueError("Scorer needs at least one signal.")
        self._signals = tuple(signals)

    def score(self, context: ScoringContext) -> ScoreResult:
        results: list[SignalResult] = []
        missing: list[str] = []
        total_possible = 0
        in_play = 0

        for signal in self._signals:
            weighted_max = self._max_points_for(signal, context)
            if weighted_max <= 0:
                continue
            total_possible += weighted_max
            in_play += 1

            outcome = signal.evaluate(context)
            if outcome is None:
                missing.append(signal.key)
                continue
            results.append(self._reweigh(outcome, weighted_max))

        available = sum(result.max_points for result in results)
        earned = sum(result.points for result in results)

        score = round(MAX_SCORE * earned / available, 1) if available else None
        confidence = available / total_possible if total_possible else 0.0

        log.debug(
            "scored",
            company=context.facts.name,
            score=score,
            confidence=round(confidence, 2),
            missing=missing,
        )
        return ScoreResult(
            score=score,
            confidence=round(confidence, 3),
            reasons=sorted(results, key=lambda result: result.points, reverse=True),
            missing_signals=missing,
            total_signals=in_play,
        )

    @staticmethod
    def _max_points_for(signal: Signal, context: ScoringContext) -> int:
        """A Buy Box may re-weight, or switch off, any signal."""
        override = context.criteria.weights.get(signal.key)
        return signal.max_points if override is None else max(0, int(override))

    @staticmethod
    def _reweigh(result: SignalResult, weighted_max: int) -> SignalResult:
        """Scale a signal's points when the user changed its weight."""
        if weighted_max == result.max_points:
            return result
        ratio = result.points / result.max_points if result.max_points else 0.0
        return result.model_copy(
            update={"points": round(ratio * weighted_max, 2), "max_points": weighted_max}
        )
