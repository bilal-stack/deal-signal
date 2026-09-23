"""Estimating revenue from headcount.

A buyer's first question is "how big is it", and almost no small business publishes
revenue. The defensible approximation is headcount multiplied by a revenue-per-
employee band for that industry.

Three rules keep it honest:

* It only runs when headcount is actually known. No headcount, no estimate, and the
  revenue signal abstains rather than inventing a number.
* The result is a range with the arithmetic and the benchmark's own source attached,
  so the UI can show where a figure came from instead of presenting it as fact.
* The benchmarks live in data/revenue_per_employee.json, and each one
  states its provenance. Rule-of-thumb entries say so; measured ones name the
  dataset. `scripts/fetch_benchmarks.py` replaces them with Census figures.
"""

from __future__ import annotations

import json
import os
from collections.abc import Sequence
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict

from dealsignal.matching.merge import confidence_of
from dealsignal.models.company import Company
from dealsignal.models.enums import SourceName
from dealsignal.repositories.field_value import FieldValueRepository
from dealsignal.services.facts import employee_estimate, headcount_basis

MILLION = 1_000_000
FIELD = "revenue_estimate"

BENCHMARKS_PATH = Path(
    os.environ.get("REVENUE_BENCHMARKS_PATH")
    or Path(__file__).resolve().parent.parent / "data" / "revenue_per_employee.json"
)
"""Ships with the package, so it needs no mount. Override the path to use figures
produced by scripts/fetch_benchmarks.py. A missing file is not fatal: the wide
default is used, and it says so."""

FALLBACK = {"low": 80_000, "high": 160_000, "source": "wide default, no benchmark file found"}


class Benchmark(BaseModel):
    """Revenue per employee for one industry, and where the figures came from."""

    model_config = ConfigDict(frozen=True)

    low: int
    high: int
    source: str


class RevenueEstimate(BaseModel):
    """An estimated range, and the sentence explaining how it was reached."""

    model_config = ConfigDict(frozen=True)

    low: int
    high: int
    method: str

    @property
    def midpoint(self) -> int:
        return (self.low + self.high) // 2


def _load(path: Path) -> tuple[dict[str, Benchmark], Benchmark]:
    try:
        raw: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}, Benchmark(**FALLBACK)

    by_industry = {
        entry["industry"]: Benchmark(low=entry["low"], high=entry["high"], source=entry["source"])
        for entry in raw.get("benchmarks", [])
    }
    default = raw.get("default") or FALLBACK
    return by_industry, Benchmark(
        low=default["low"], high=default["high"], source=default["source"]
    )


@lru_cache(maxsize=1)
def benchmarks() -> tuple[dict[str, Benchmark], Benchmark]:
    """The benchmark table, read once per process."""
    return _load(BENCHMARKS_PATH)


def benchmark_for(industry_keys: Sequence[str]) -> Benchmark:
    """The first industry we have a benchmark for, or the wide default."""
    table, default = benchmarks()
    for key in industry_keys:
        if key in table:
            return table[key]
    return default


def estimate_revenue(
    *,
    employee_count: int | None,
    industry_keys: Sequence[str] = (),
    headcount_basis: str | None = None,
) -> RevenueEstimate | None:
    """Revenue range from headcount, or None when headcount is unknown.

    Returning None is the point: an unknown size stays unknown rather than becoming
    a confident-looking guess.
    """
    if employee_count is None or employee_count <= 0:
        return None

    benchmark = benchmark_for(industry_keys)
    staff = f"{employee_count} staff" + (f" ({headcount_basis})" if headcount_basis else "")
    return RevenueEstimate(
        low=employee_count * benchmark.low,
        high=employee_count * benchmark.high,
        method=(
            f"{staff} x ${benchmark.low // 1000}k-${benchmark.high // 1000}k "
            f"revenue per employee ({benchmark.source})"
        ),
    )


async def record_revenue_estimate(
    company: Company, fields: FieldValueRepository, *, observed_at: datetime
) -> None:
    """Estimate revenue from what we now know about headcount, and record how.

    Called whenever headcount may have changed. Stored as its own field value, so the
    UI shows it as our estimate with its arithmetic, never as a published figure.
    """
    estimate = estimate_revenue(
        employee_count=employee_estimate(company),
        industry_keys=company.industry_keys or [],
        headcount_basis=headcount_basis(company),
    )
    if estimate is None:
        return

    company.revenue_low = estimate.low
    company.revenue_high = estimate.high
    await fields.record(
        company_id=company.id,
        field=FIELD,
        value={"low": estimate.low, "high": estimate.high},
        source=SourceName.ESTIMATE,
        observed_at=observed_at,
        confidence=confidence_of(SourceName.ESTIMATE),
        evidence=estimate.method,
    )
