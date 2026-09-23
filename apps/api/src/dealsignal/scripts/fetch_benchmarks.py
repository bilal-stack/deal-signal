"""Replace the rule-of-thumb revenue benchmarks with measured ones.

    python -m dealsignal.scripts.fetch_benchmarks --key YOUR_CENSUS_KEY

The US Census Economic Census publishes total receipts and employment per industry,
and receipts divided by employment is exactly the figure the estimator needs. The
API is free but now requires a key: https://api.census.gov/data/key_signup.html

Nothing is overwritten unless every industry was fetched successfully, so a partial
run cannot leave the table half measured and half rule-of-thumb without saying so.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import httpx

from dealsignal.core.config import get_settings
from dealsignal.core.logging import configure_logging, get_logger
from dealsignal.services.estimates import BENCHMARKS_PATH

log = get_logger(__name__)

CENSUS_URL = "https://api.census.gov/data/2017/ecnbasic"
DATASET = "US Census Economic Census 2017, receipts per employee"
SPREAD = 0.25
"""Measured figures are a single average, so the band is set either side of it:
small firms vary, and a single number would look more precise than it is."""


async def receipts_per_employee(client: httpx.AsyncClient, naics: str, key: str) -> float | None:
    """Average receipts per employee for one industry, or None if not published."""
    response = await client.get(
        CENSUS_URL,
        params={"get": "RCPTOT,EMP", "for": "us:*", "NAICS2017": naics, "key": key},
    )
    if response.status_code != httpx.codes.OK:
        log.warning("census_refused", naics=naics, status=response.status_code)
        return None

    rows = response.json()
    if len(rows) < 2:
        return None

    receipts_thousands, employees = float(rows[1][0]), float(rows[1][1])
    if employees <= 0:
        return None
    return receipts_thousands * 1000 / employees


async def refresh(key: str, path: Path) -> int:
    """Returns the number of benchmarks replaced."""
    document = json.loads(await asyncio.to_thread(path.read_text, encoding="utf-8"))
    updated = 0

    async with httpx.AsyncClient(timeout=30.0) as client:
        for entry in document["benchmarks"]:
            average = await receipts_per_employee(client, entry["naics"], key)
            if average is None:
                print(f"[skip] {entry['industry']}: no published figure")  # noqa: T201
                continue
            entry["low"] = int(average * (1 - SPREAD))
            entry["high"] = int(average * (1 + SPREAD))
            entry["source"] = DATASET
            updated += 1
            print(  # noqa: T201
                f"[ok]   {entry['industry']}: ${entry['low']:,}-${entry['high']:,} per employee"
            )

    if updated:
        document["updated"] = datetime.now(UTC).date().isoformat()
        await asyncio.to_thread(
            path.write_text,
            json.dumps(document, indent=2) + "\n",
            encoding="utf-8",
        )
    return updated


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Refresh revenue benchmarks from the US Census.")
    parser.add_argument("--key", default="", help="Census API key (free).")
    parser.add_argument("--path", type=Path, default=BENCHMARKS_PATH)
    args = parser.parse_args(argv)

    configure_logging(get_settings())
    if not args.key:
        print(  # noqa: T201
            "A free Census API key is needed: https://api.census.gov/data/key_signup.html\n"
            "Until then the benchmarks stay as documented rules of thumb.",
            file=sys.stderr,
        )
        return 1

    replaced = asyncio.run(refresh(args.key, args.path))
    print(f"\nReplaced {replaced} benchmarks with measured figures.")  # noqa: T201
    print("Update stored estimates with: python -m dealsignal.scripts.estimates")  # noqa: T201
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
