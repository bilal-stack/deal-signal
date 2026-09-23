"""Release discovery and query building, without touching the network."""

from __future__ import annotations

import pytest

from dealsignal.sources.industries import resolve
from dealsignal.sources.overture import build_query, parse_release_listing
from dealsignal.sources.regions import get_region

LISTING = """<?xml version="1.0" encoding="UTF-8"?>
<ListBucketResult xmlns="http://s3.amazonaws.com/doc/2006-03-01/">
  <Name>overturemaps-us-west-2</Name>
  <Prefix>release/</Prefix>
  <CommonPrefixes><Prefix>release/2026-07-23.0/</Prefix></CommonPrefixes>
  <CommonPrefixes><Prefix>release/2026-08-20.2/</Prefix></CommonPrefixes>
  <CommonPrefixes><Prefix>release/2026-08-20.10/</Prefix></CommonPrefixes>
  <CommonPrefixes><Prefix>release/not-a-release/</Prefix></CommonPrefixes>
</ListBucketResult>
"""


def test_releases_are_ordered_by_date_then_build_number() -> None:
    assert parse_release_listing(LISTING) == ["2026-07-23.0", "2026-08-20.2", "2026-08-20.10"]


def test_entries_that_are_not_releases_are_ignored() -> None:
    assert "not-a-release" not in "".join(parse_release_listing(LISTING))


def test_an_empty_listing_yields_nothing() -> None:
    empty = (
        '<?xml version="1.0"?><ListBucketResult xmlns="http://s3.amazonaws.com/doc/2006-03-01/" />'
    )

    assert parse_release_listing(empty) == []


def test_the_query_filters_by_bounding_box_and_categories() -> None:
    industry = resolve("HVAC")
    region = get_region("dallas")
    assert industry is not None

    sql = build_query("s3://bucket/places/*", region, industry.categories, limit=50)

    assert "s3://bucket/places/*" in sql
    assert "bbox.xmin >= -97.55" in sql
    assert "bbox.ymax <= 33.1" in sql
    assert "'hvac_services'" in sql
    assert "LIMIT 50" in sql


def test_the_query_looks_at_alternate_categories_too() -> None:
    industry = resolve("plumbing")
    assert industry is not None

    sql = build_query("s3://bucket/*", get_region("houston"), industry.categories, limit=10)

    assert "categories.primary IN" in sql
    assert "list_has_any(categories.alternate" in sql


def test_unknown_regions_say_what_is_available() -> None:
    with pytest.raises(KeyError, match="Known regions"):
        get_region("atlantis")
