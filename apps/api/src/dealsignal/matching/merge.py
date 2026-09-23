"""How far each source is trusted when two of them disagree about a field."""

from __future__ import annotations

from dealsignal.models.enums import SourceName

SOURCE_CONFIDENCE: dict[SourceName, float] = {
    SourceName.COMPANIES_HOUSE: 0.95,
    SourceName.RECHERCHE_ENTREPRISES: 0.95,
    SourceName.WEBSITE: 0.85,
    SourceName.RDAP: 0.8,
    SourceName.OVERTURE: 0.7,
    SourceName.ESTIMATE: 0.5,
}
"""How much each source is trusted. An official register beats a map listing."""

DEFAULT_CONFIDENCE = 0.5


def confidence_of(source: SourceName) -> float:
    return SOURCE_CONFIDENCE.get(source, DEFAULT_CONFIDENCE)
