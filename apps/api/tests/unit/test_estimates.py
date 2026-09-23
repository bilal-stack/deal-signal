"""Revenue estimates: useful when headcount is known, absent when it is not."""

from __future__ import annotations

import pytest

from dealsignal.services.estimates import benchmark_for, benchmarks, estimate_revenue

HVAC = ["hvac"]


def test_headcount_becomes_a_revenue_range() -> None:
    estimate = estimate_revenue(employee_count=25, industry_keys=HVAC)

    assert estimate is not None
    assert estimate.low == 25 * 150_000
    assert estimate.high == 25 * 250_000


def test_the_method_is_carried_with_the_number() -> None:
    estimate = estimate_revenue(employee_count=25, industry_keys=HVAC)

    assert estimate is not None
    assert "25 staff" in estimate.method
    assert "per employee" in estimate.method


@pytest.mark.parametrize("headcount", [None, 0, -3])
def test_no_headcount_means_no_estimate(headcount: int | None) -> None:
    """The rule that matters: an unknown size stays unknown."""
    assert estimate_revenue(employee_count=headcount, industry_keys=HVAC) is None


def test_an_unknown_industry_uses_the_wider_default_band() -> None:
    _, default = benchmarks()
    estimate = estimate_revenue(employee_count=10, industry_keys=["basket_weaving"])

    assert estimate is not None
    assert estimate.low == 10 * default.low
    assert estimate.high == 10 * default.high


def test_no_industry_at_all_still_estimates() -> None:
    assert estimate_revenue(employee_count=10) is not None


def test_the_midpoint_sits_between_the_bounds() -> None:
    estimate = estimate_revenue(employee_count=12, industry_keys=HVAC)

    assert estimate is not None
    assert estimate.low < estimate.midpoint < estimate.high


def test_every_benchmark_is_a_sane_widening_range() -> None:
    table, default = benchmarks()
    for industry, benchmark in {**table, "default": default}.items():
        assert 0 < benchmark.low < benchmark.high, f"{industry} has a broken band"
        assert benchmark.high <= 500_000, f"{industry} looks too high for a small firm"


def test_every_benchmark_says_where_its_figures_came_from() -> None:
    """A number without a provenance is how an estimate gets mistaken for a fact."""
    table, default = benchmarks()
    for benchmark in [*table.values(), default]:
        assert benchmark.source.strip()


def test_the_method_names_the_benchmark_source() -> None:
    estimate = estimate_revenue(employee_count=25, industry_keys=HVAC)

    assert estimate is not None
    assert benchmark_for(HVAC).source in estimate.method


def test_a_headcount_from_a_band_says_so() -> None:
    """Five staff is the midpoint of a 1-9 band, not a count, and the method must say it."""
    estimate = estimate_revenue(
        employee_count=5,
        industry_keys=HVAC,
        headcount_basis="midpoint of the register's 1-9 band",
    )

    assert estimate is not None
    assert estimate.method.startswith("5 staff (midpoint of the register's 1-9 band) x ")
