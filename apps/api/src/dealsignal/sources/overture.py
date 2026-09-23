"""Overture Maps as our places source.

Overture publishes an open, permissively licensed dataset of places as partitioned
parquet on public S3. DuckDB reads it directly with predicate pushdown, so a city
sized bounding box costs a single query and no bulk download, and the licence lets
the resulting demo dataset live in this repository.

DuckDB is synchronous, so the query runs in a worker thread.
"""

from __future__ import annotations

import asyncio
import re
from typing import Any

import httpx

from dealsignal.core.config import Settings
from dealsignal.core.errors import ExternalServiceError
from dealsignal.core.logging import get_logger
from dealsignal.models.enums import Country, SourceName
from dealsignal.sources.base import PlaceRecord, PlaceSource
from dealsignal.sources.industries import Industry
from dealsignal.sources.overture_parsing import to_place_record
from dealsignal.sources.regions import Region

log = get_logger(__name__)

BUCKET_URL = "https://overturemaps-us-west-2.s3.amazonaws.com"
RELEASE_LISTING_URL = f"{BUCKET_URL}/?list-type=2&prefix=release/&delimiter=/"
DATASET_TEMPLATE = "s3://overturemaps-us-west-2/release/{release}/theme=places/type=place/*"
RELEASE_PATTERN = re.compile(r"<Prefix>release/(\d{4}-\d{2}-\d{2})\.(\d+)/</Prefix>")
LISTING_TIMEOUT_SECONDS = 20.0
QUERY_TIMEOUT_SECONDS = 300.0
SAFE_SLUG = re.compile(r"[a-z0-9_]+")
"""Category slugs are interpolated into SQL, so they are checked to be plain
identifiers first. Everything else in the query is a float from our own regions."""


def parse_release_listing(xml_text: str) -> list[str]:
    """Pull release names out of the bucket listing, oldest first.

    Sorting is by date then build number, so 2026-08-20.10 follows 2026-08-20.2
    instead of sorting before it as plain text would.
    """
    releases = [
        (date, int(build), f"{date}.{build}") for date, build in RELEASE_PATTERN.findall(xml_text)
    ]
    return [name for _, _, name in sorted(releases)]


def build_query(dataset: str, region: Region, categories: frozenset[str], limit: int) -> str:
    """The SQL for one region-and-industry slice.

    The bbox columns are what make this cheap: parquet row groups outside the box
    are skipped without being read. There is deliberately no ORDER BY: DuckDB keeps
    file order by default (preserve_insertion_order), so a load is already repeatable
    for a given release, and LIMIT can stop reading as soon as it has enough rows.
    Sorting would force a read of every matching place in the area first.
    """
    if not all(SAFE_SLUG.fullmatch(category) for category in categories):
        raise ValueError("Category slugs must be plain identifiers.")
    category_list = ", ".join(f"'{category}'" for category in sorted(categories))
    return f"""
        SELECT id,
               names,
               categories,
               addresses,
               websites,
               phones,
               confidence,
               bbox.xmin AS longitude,
               bbox.ymin AS latitude
        FROM read_parquet('{dataset}', hive_partitioning = 1)  -- noqa
        WHERE bbox.xmin >= {region.west}
          AND bbox.xmax <= {region.east}
          AND bbox.ymin >= {region.south}
          AND bbox.ymax <= {region.north}
          AND (
                categories.primary IN ({category_list})
             OR list_has_any(categories.alternate, [{category_list}])
          )
        LIMIT {int(limit)}
    """


class OverturePlacesSource(PlaceSource):
    """Places from the Overture open dataset."""

    name = SourceName.OVERTURE
    countries = frozenset({Country.US, Country.GB, Country.FR})

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._dataset: str | None = settings.overture_dataset_url or None

    async def is_available(self) -> bool:
        """True when we can name a dataset to read."""
        try:
            await self._resolve_dataset()
        except ExternalServiceError:
            return False
        return True

    async def search(self, *, industry: Industry, region: Region, limit: int) -> list[PlaceRecord]:
        dataset = await self._resolve_dataset()
        sql = build_query(dataset, region, industry.categories, limit)

        log.info("overture_search", industry=industry.key, region=region.key, dataset=dataset)
        rows = await asyncio.wait_for(
            asyncio.to_thread(self._run_query, sql), timeout=QUERY_TIMEOUT_SECONDS
        )

        records = [to_place_record(row, country=region.country) for row in rows]
        found = [record for record in records if record is not None]
        log.info("overture_search_done", rows=len(rows), usable=len(found))
        return found

    async def _resolve_dataset(self) -> str:
        """The parquet path: an override, a pinned release, or the newest published."""
        if self._dataset:
            return self._dataset
        if self._settings.overture_release:
            self._dataset = DATASET_TEMPLATE.format(release=self._settings.overture_release)
            return self._dataset

        try:
            async with httpx.AsyncClient(timeout=LISTING_TIMEOUT_SECONDS) as client:
                response = await client.get(RELEASE_LISTING_URL)
                response.raise_for_status()
                releases = parse_release_listing(response.text)
        except httpx.HTTPError as exc:
            raise ExternalServiceError(
                "Could not reach the Overture data catalogue. Set OVERTURE_RELEASE to "
                "a known release, or OVERTURE_DATASET_URL to a local copy.",
                source=SourceName.OVERTURE,
            ) from exc

        if not releases:
            raise ExternalServiceError(
                "The Overture catalogue listed no releases.",
                source=SourceName.OVERTURE,
                retryable=False,
            )

        self._dataset = DATASET_TEMPLATE.format(release=releases[-1])
        log.info("overture_release_selected", release=releases[-1])
        return self._dataset

    @staticmethod
    def _run_query(sql: str) -> list[dict[str, Any]]:
        """Blocking DuckDB query, returning rows as dictionaries."""
        import duckdb

        connection = duckdb.connect()
        try:
            connection.execute("INSTALL httpfs; LOAD httpfs; SET s3_region = 'us-west-2';")
            cursor = connection.execute(sql)
            columns = [description[0] for description in cursor.description or []]
            return [dict(zip(columns, row, strict=True)) for row in cursor.fetchall()]
        except Exception as exc:  # duckdb raises its own hierarchy
            raise ExternalServiceError(
                f"Reading the Overture dataset failed: {exc}",
                source=SourceName.OVERTURE,
            ) from exc
        finally:
            connection.close()
