"""The demo dataset: exported from a working database, loaded into a fresh one.

    python -m dealsignal.scripts.demo_data load            # into an empty database
    python -m dealsignal.scripts.demo_data load --replace  # over what is there
    python -m dealsignal.scripts.demo_data export          # refresh the committed copy

Building the data from scratch means about 20 minutes of Overture queries plus the
register and domain lookups; the committed copy loads in seconds. It holds every
company with its facts and where each came from, the owners the registers list, what
each enrichment job tried, the duplicate review queue, the pipeline, and a few Buy
Boxes to start from. Scores are not stored: every search recomputes them.

The export also writes each Buy Box's ranked results to demo_data/leads/*.csv, so the
leads can be read on GitHub without running anything.
"""

from __future__ import annotations

import argparse
import asyncio
import gzip
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from dealsignal.core.config import get_settings
from dealsignal.core.logging import configure_logging
from dealsignal.db.session import dispose_engine, init_engine, session_scope
from dealsignal.models.buy_box import BuyBox
from dealsignal.models.enums import BuyBoxMode, Country
from dealsignal.schemas.buy_box import BuyBoxCreate
from dealsignal.services.buy_boxes import build_buy_box
from dealsignal.services.export import LeadExport, to_csv

DEMO_DIR = Path(__file__).resolve().parents[3] / "demo_data"
DATASET = DEMO_DIR / "dealsignal_demo.json.gz"
LEADS_DIR = DEMO_DIR / "leads"
FORMAT_VERSION = 1

TABLES: tuple[str, ...] = (
    "buy_boxes",
    "companies",
    "field_values",
    "people",
    "enrichment_attempts",
    "duplicate_candidates",
    "pipeline_items",
    "suppression_entries",
)
"""Parents before children, so every foreign key finds its row on load."""

DERIVED_TABLES = ("scores",)
"""Emptied on --replace, never exported: recomputed by the next search."""

DEMO_BUY_BOXES: tuple[BuyBoxCreate, ...] = (
    BuyBoxCreate(
        name="HVAC firms to buy, Fort Worth",
        industries=["hvac"],
        countries=[Country.US],
        city="Fort Worth",
        revenue_min=1_000_000,
        revenue_max=10_000_000,
        employees_min=5,
        employees_max=50,
    ),
    BuyBoxCreate(
        name="Plumbing firms to buy, Texas",
        industries=["plumbing"],
        countries=[Country.US],
        revenue_min=1_000_000,
        revenue_max=10_000_000,
    ),
    BuyBoxCreate(
        name="Heating firms to buy, Lyon",
        industries=["hvac"],
        countries=[Country.FR],
        employees_min=5,
        employees_max=50,
    ),
    BuyBoxCreate(
        name="Accountancy practices to buy, Manchester",
        industries=["accounting"],
        countries=[Country.GB],
    ),
    BuyBoxCreate(
        name="Dental practices to sell to, Fort Worth",
        mode=BuyBoxMode.SALES,
        industries=["dental"],
        countries=[Country.US],
        city="Fort Worth",
    ),
)
"""The starting points a new user sees: one per region, and one in sales mode."""


def known_table(table: str) -> str:
    """Table names only ever come from TABLES, never from input. Checked anyway, since
    a name cannot be a bound parameter and has to be written into the SQL."""
    if table not in (*TABLES, *DERIVED_TABLES):
        raise ValueError(f"Not a demo dataset table: {table}")
    return table


async def current_revision(session: AsyncSession) -> str:
    revision = await session.scalar(text("select version_num from alembic_version"))
    return str(revision)


async def ensure_demo_buy_boxes(session: AsyncSession) -> list[BuyBox]:
    """The curated Buy Boxes, created if missing, so the export always has them."""
    existing = {
        buy_box.name: buy_box
        for buy_box in await session.scalars(
            select(BuyBox).where(BuyBox.name.in_([criteria.name for criteria in DEMO_BUY_BOXES]))
        )
    }
    boxes = []
    for criteria in DEMO_BUY_BOXES:
        buy_box = existing.get(criteria.name)
        if buy_box is None:
            buy_box = build_buy_box(criteria)
            session.add(buy_box)
        boxes.append(buy_box)
    await session.flush()
    return boxes


async def table_rows(session: AsyncSession, table: str, names: list[str]) -> list[Any]:
    """Every row as JSON, which Postgres converts back exactly on load."""
    query = f"select coalesce(json_agg(t), '[]'::json)::text from {known_table(table)} t"  # noqa: S608
    if table == "buy_boxes":
        raw = await session.scalar(text(f"{query} where t.name = any(:names)"), {"names": names})
    else:
        raw = await session.scalar(text(query))
    rows: list[Any] = json.loads(raw or "[]")
    return rows


def leads_filename(buy_box_name: str) -> str:
    slug = "".join(char.lower() if char.isalnum() else "-" for char in buy_box_name)
    return "-".join(part for part in slug.split("-") if part) + ".csv"


class DemoDataError(Exception):
    """Why a load cannot go ahead, in words the person running it can act on."""


async def snapshot(session: AsyncSession, *, buy_box_names: list[str]) -> dict[str, Any]:
    """Everything the demo needs, as plain JSON."""
    tables = {table: await table_rows(session, table, buy_box_names) for table in TABLES}
    return {
        "format": FORMAT_VERSION,
        "alembic_revision": await current_revision(session),
        "exported_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "counts": {table: len(rows) for table, rows in tables.items()},
        "tables": tables,
    }


async def restore(session: AsyncSession, dataset: dict[str, Any], *, replace: bool) -> None:
    """Load a snapshot. Refuses a different schema, and existing data unless told."""
    revision = await current_revision(session)
    if revision != dataset["alembic_revision"]:
        raise DemoDataError(
            f"The dataset was exported at schema {dataset['alembic_revision']}, but the "
            f"database is at {revision}. Start the api once so it migrates, then retry."
        )
    existing = int(await session.scalar(text("select count(*) from companies")) or 0)
    if existing and not replace:
        raise DemoDataError(
            f"The database already holds {existing} companies. "
            "Run with --replace to overwrite them with the demo dataset."
        )
    if replace:
        everything = ", ".join(known_table(name) for name in (*TABLES, *DERIVED_TABLES))
        await session.execute(text(f"truncate {everything} cascade"))

    for table in TABLES:
        await session.execute(
            text(
                f"insert into {known_table(table)} select * from "  # noqa: S608
                f"json_populate_recordset(null::{table}, cast(:rows as json))"
            ),
            {"rows": json.dumps(dataset["tables"][table])},
        )


def describe(dataset: dict[str, Any]) -> str:
    return ", ".join(f"{count} {table}" for table, count in dataset["counts"].items())


async def export() -> None:
    async with session_scope() as session:
        boxes = await ensure_demo_buy_boxes(session)
        dataset = await snapshot(session, buy_box_names=[buy_box.name for buy_box in boxes])

        LEADS_DIR.mkdir(parents=True, exist_ok=True)
        for buy_box in boxes:
            rows = await LeadExport(session).rows(buy_box)
            (LEADS_DIR / leads_filename(buy_box.name)).write_bytes(to_csv(rows))
            print(f"{buy_box.name}: {len(rows)} ranked leads")  # noqa: T201

    DEMO_DIR.mkdir(parents=True, exist_ok=True)
    with gzip.open(DATASET, "wt", encoding="utf-8") as file:
        json.dump(dataset, file, ensure_ascii=False, separators=(",", ":"))
    print(f"Wrote {DATASET.name}: {describe(dataset)}")  # noqa: T201


async def load(*, replace: bool) -> int:
    with gzip.open(DATASET, "rt", encoding="utf-8") as file:
        dataset: dict[str, Any] = json.load(file)
    try:
        async with session_scope() as session:
            await restore(session, dataset, replace=replace)
    except DemoDataError as error:
        print(error, file=sys.stderr)  # noqa: T201
        return 1
    print(f"Loaded the demo dataset from {dataset['exported_at']}: {describe(dataset)}.")  # noqa: T201
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Load or export the demo dataset.")
    parser.add_argument("action", choices=("load", "export"))
    parser.add_argument("--replace", action="store_true", help="load over existing data")
    args = parser.parse_args(argv)

    settings = get_settings()
    configure_logging(settings)

    async def run() -> int:
        init_engine(settings)
        try:
            if args.action == "export":
                await export()
                return 0
            return await load(replace=args.replace)
        finally:
            await dispose_engine()

    return asyncio.run(run())


if __name__ == "__main__":
    raise SystemExit(main())
