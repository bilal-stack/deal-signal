"""Regions we can load places for.

A region is a bounding box plus the country it belongs to. Keeping them in code
means `make seed REGION=dallas` needs no extra configuration, and the demo dataset
is reproducible by anyone who clones the repo.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from dealsignal.models.enums import Country


class Region(BaseModel):
    """A named bounding box: west, south, east, north in degrees."""

    model_config = ConfigDict(frozen=True)

    key: str
    label: str
    country: Country
    west: float
    south: float
    east: float
    north: float


REGIONS: dict[str, Region] = {
    region.key: region
    for region in (
        Region(
            key="dallas",
            label="Dallas-Fort Worth, TX",
            country=Country.US,
            west=-97.55,
            south=32.55,
            east=-96.45,
            north=33.10,
        ),
        Region(
            key="houston",
            label="Houston, TX",
            country=Country.US,
            west=-95.85,
            south=29.52,
            east=-95.02,
            north=30.11,
        ),
        Region(
            key="manchester",
            label="Manchester, UK",
            country=Country.GB,
            west=-2.36,
            south=53.38,
            east=-2.12,
            north=53.55,
        ),
        Region(
            key="lyon",
            label="Lyon, France",
            country=Country.FR,
            west=4.76,
            south=45.70,
            east=4.92,
            north=45.81,
        ),
    )
}


def get_region(key: str) -> Region:
    """Look up a region, listing the alternatives when the key is wrong."""
    try:
        return REGIONS[key]
    except KeyError:
        known = ", ".join(sorted(REGIONS))
        raise KeyError(f"Unknown region {key!r}. Known regions: {known}.") from None
