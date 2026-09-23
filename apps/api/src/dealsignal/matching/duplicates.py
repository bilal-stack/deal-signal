"""Deciding whether two records are the same business.

Candidates come from the database (same domain, same phone, or nearby with a
similar name). This module only scores a pair and says what to do about it, so the
thresholds can be tuned against labelled examples without touching any SQL.
"""

from __future__ import annotations

from math import asin, cos, radians, sin, sqrt

from pydantic import BaseModel, ConfigDict
from rapidfuzz import fuzz

from dealsignal.matching.normalize import compact_name, normalize_name

AUTO_MERGE = 0.9
"""At or above this, two records are the same business."""

NEEDS_REVIEW = 0.7
"""Between this and AUTO_MERGE, a person decides."""

SAME_PLACE_METRES = 150.0
EARTH_RADIUS_METRES = 6_371_000.0

SAME_NAME_SIMILARITY = 0.6
"""Two names on one website below this are different businesses sharing it."""

MIN_CONTAINED_NAME_CHARS = 4
"""A name inside another counts as the same name only when it is this long."""

SAME_BUSINESS_RADIUS_METRES = 25_000.0
"""One website's listings further apart than this are branches or franchisees."""

SHARED_WEBSITE_REVIEW_SCORE = 0.8

PHONE_WEIGHT = 0.5
NAME_WEIGHT = 0.35
DISTANCE_WEIGHT = 0.15


class Candidate(BaseModel):
    """The few fields duplicate detection actually needs."""

    model_config = ConfigDict(frozen=True)

    name: str
    domain: str | None = None
    phone_e164: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    website_path: str = ""
    """The page the listing points at, "" for the home page. Franchises and chains
    point each location at its own page on one shared website."""


class MatchDecision(BaseModel):
    model_config = ConfigDict(frozen=True)

    score: float
    merge: bool
    review: bool
    reason: str


def distance_metres(left: Candidate, right: Candidate) -> float | None:
    """Great-circle distance, or None when either side has no coordinates."""
    if None in (left.latitude, left.longitude, right.latitude, right.longitude):
        return None

    lat1, lon1 = radians(float(left.latitude or 0)), radians(float(left.longitude or 0))
    lat2, lon2 = radians(float(right.latitude or 0)), radians(float(right.longitude or 0))
    half_chord = sin((lat2 - lat1) / 2) ** 2 + cos(lat1) * cos(lat2) * sin((lon2 - lon1) / 2) ** 2
    return 2 * EARTH_RADIUS_METRES * asin(sqrt(half_chord))


def name_similarity(left: str, right: str) -> float:
    """0.0 to 1.0 on the normalised names, ignoring word order."""
    return fuzz.token_set_ratio(normalize_name(left), normalize_name(right)) / 100.0


def names_agree(left: str, right: str) -> bool:
    """Two spellings of one business name, rather than two businesses.

    "Andrew's Air Conditioning" and "Andrews Air Conditioning & Refrigeration" agree;
    "Kristy Hong" and "Kreating Smiles Pediatric Dentistry" do not.
    """
    shorter, longer = sorted((compact_name(left), compact_name(right)), key=len)
    if len(shorter) >= MIN_CONTAINED_NAME_CHARS and shorter in longer:
        return True
    return name_similarity(left, right) >= SAME_NAME_SIMILARITY


def website_doubt(left: Candidate, right: Candidate) -> str | None:
    """Why two listings of one website might still be two businesses, if they might.

    A website usually belongs to one business, but a chain or a franchise points
    each location at its own page, and a practice lists each dentist separately.
    """
    if left.website_path and right.website_path and left.website_path != right.website_path:
        return "Same website, but different location pages: a chain or a franchise?"
    if not names_agree(left.name, right.name):
        return "Same website, but different business names"
    metres = distance_metres(left, right)
    if metres is not None and metres > SAME_BUSINESS_RADIUS_METRES:
        return f"Same website, but {round(metres / 1000)} km apart: a chain or a franchise?"
    return None


def compare(left: Candidate, right: Candidate) -> MatchDecision:
    """Score a pair and say whether to merge, review, or leave them apart.

    A business's own website is strong evidence, and decisive when the page, the
    name and the place agree too; otherwise a person decides. Shared hosts never
    reach here: `identity_domain` gives them no domain. A shared phone is nearly as
    strong. Otherwise the name has to carry it, helped by being at the same address.
    """
    if left.domain and right.domain and left.domain == right.domain:
        doubt = website_doubt(left, right)
        if doubt is None:
            return MatchDecision(score=1.0, merge=True, review=False, reason="Same website domain")
        return MatchDecision(
            score=SHARED_WEBSITE_REVIEW_SCORE, merge=False, review=True, reason=doubt
        )

    score = 0.0
    reasons: list[str] = []

    if left.phone_e164 and right.phone_e164 and left.phone_e164 == right.phone_e164:
        score += PHONE_WEIGHT
        reasons.append("same phone number")

    similarity = name_similarity(left.name, right.name)
    score += similarity * NAME_WEIGHT
    if similarity >= 0.9:
        reasons.append("near-identical name")

    metres = distance_metres(left, right)
    if metres is not None and metres <= SAME_PLACE_METRES:
        score += DISTANCE_WEIGHT
        reasons.append(f"{round(metres)} m apart")

    score = min(score, 1.0)
    return MatchDecision(
        score=round(score, 3),
        merge=score >= AUTO_MERGE,
        review=NEEDS_REVIEW <= score < AUTO_MERGE,
        reason=", ".join(reasons).capitalize() if reasons else "No matching identifiers",
    )
