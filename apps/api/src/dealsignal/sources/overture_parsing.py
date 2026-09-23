"""Turning an Overture places row into a PlaceRecord.

Kept apart from the DuckDB query so the mapping can be tested without a network
call or a database. Overture nests most useful fields inside structs, and any of
them can be absent, so every read goes through a helper that returns None rather
than inventing a value.
"""

from __future__ import annotations

from typing import Any

from dealsignal.models.enums import Country, SourceName
from dealsignal.sources.base import PlaceRecord

MIN_CONFIDENCE = 0.5
"""Overture scores each place. Below this the record is too doubtful to show."""


def _first(value: Any) -> Any | None:
    """Overture stores repeated fields as lists; we want the primary entry."""
    if isinstance(value, (list, tuple)):
        return value[0] if value else None
    return value


def _text(value: Any) -> str | None:
    """A trimmed string, or None. Empty strings are not data."""
    text = _first(value)
    if text is None:
        return None
    cleaned = str(text).strip()
    return cleaned or None


def _nested(row: dict[str, Any], *path: str) -> Any | None:
    """Walk a nested struct safely: _nested(row, 'names', 'primary')."""
    current: Any = row
    for key in path:
        if current is None:
            return None
        current = current.get(key) if isinstance(current, dict) else None
    return current


def category_of(row: dict[str, Any]) -> str | None:
    """The primary Overture category, for example 'hvac_services'."""
    return _text(_nested(row, "categories", "primary"))


def to_place_record(row: dict[str, Any], *, country: Country) -> PlaceRecord | None:
    """Map one Overture row, or None when it is unusable.

    A row is unusable when it has no id, no name, or a confidence Overture itself
    considers low. Returning None here is honest: the row is dropped, not guessed at.
    """
    external_id = _text(row.get("id"))
    name = _text(_nested(row, "names", "primary"))
    if not external_id or not name:
        return None

    confidence = row.get("confidence")
    if isinstance(confidence, (int, float)) and confidence < MIN_CONFIDENCE:
        return None

    address = _first(row.get("addresses")) or {}
    if not isinstance(address, dict):
        address = {}

    return PlaceRecord(
        source=SourceName.OVERTURE,
        external_id=external_id,
        name=name,
        country=country,
        category=category_of(row),
        street=_text(address.get("freeform")),
        city=_text(address.get("locality")),
        region=_text(address.get("region")),
        postal_code=_text(address.get("postcode")),
        latitude=row.get("latitude"),
        longitude=row.get("longitude"),
        website=_text(row.get("websites")),
        phone=_text(row.get("phones")),
        raw={"confidence": confidence} if confidence is not None else {},
    )
