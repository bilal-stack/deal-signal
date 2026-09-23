"""Search responses."""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import Field

from dealsignal.schemas.common import ApiModel
from dealsignal.schemas.company import ScoreReason

if TYPE_CHECKING:
    from dealsignal.services.search import SearchOutcome


class ScoredRow(ApiModel):
    """One row of the results table: the score and why."""

    company_id: str
    name: str
    score: float | None = None
    confidence: float
    confidence_label: str
    reasons: list[ScoreReason] = Field(default_factory=list)
    missing_signals: list[str] = Field(default_factory=list)
    total_signals: int = 0
    latitude: float | None = None
    longitude: float | None = None


class SearchRead(ApiModel):
    """A finished search, including what it could not judge."""

    buy_box_id: str
    considered: int
    high_confidence: int
    withheld: int = 0
    results: list[ScoredRow]

    @classmethod
    def from_outcome(cls, outcome: SearchOutcome) -> SearchRead:
        return cls(
            buy_box_id=outcome.buy_box_id,
            considered=outcome.considered,
            high_confidence=outcome.high_confidence,
            withheld=outcome.withheld,
            results=[
                ScoredRow(
                    company_id=item.company_id,
                    name=item.name,
                    score=item.result.score,
                    confidence=item.result.confidence,
                    confidence_label=item.result.confidence_label,
                    reasons=[ScoreReason(**reason.model_dump()) for reason in item.result.reasons],
                    missing_signals=item.result.missing_signals,
                    total_signals=item.result.total_signals,
                    latitude=item.latitude,
                    longitude=item.longitude,
                )
                for item in outcome.scored
            ],
        )
