"""Turning the criteria a user submits into a saved Buy Box."""

from __future__ import annotations

from dealsignal.models.buy_box import BuyBox
from dealsignal.schemas.buy_box import BuyBoxCreate


def build_buy_box(criteria: BuyBoxCreate) -> BuyBox:
    """One place that maps criteria to the table, for the API and the demo dataset."""
    return BuyBox(
        name=criteria.name,
        mode=criteria.mode,
        industries=criteria.industries,
        countries=[str(country) for country in criteria.countries],
        city=criteria.city,
        region=criteria.region,
        radius_km=criteria.radius_km,
        revenue_min=criteria.revenue_min,
        revenue_max=criteria.revenue_max,
        employees_min=criteria.employees_min,
        employees_max=criteria.employees_max,
        exclude_pe_owned=criteria.exclude_pe_owned,
        weights=criteria.weights,
    )
