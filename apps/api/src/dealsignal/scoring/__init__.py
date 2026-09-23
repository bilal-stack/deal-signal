"""Scoring: how well a company fits, and how likely the owner is to sell."""

from dealsignal.scoring.base import Signal, SignalResult
from dealsignal.scoring.context import BuyBoxCriteria, CompanyFacts, ScoringContext
from dealsignal.scoring.scorer import Scorer, ScoreResult
from dealsignal.scoring.signals import DEFAULT_SIGNALS, TOTAL_POINTS

__all__ = [
    "DEFAULT_SIGNALS",
    "TOTAL_POINTS",
    "BuyBoxCriteria",
    "CompanyFacts",
    "ScoreResult",
    "Scorer",
    "ScoringContext",
    "Signal",
    "SignalResult",
]
