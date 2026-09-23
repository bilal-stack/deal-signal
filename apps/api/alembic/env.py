"""Alembic environment.

The database URL comes from application settings, so there is exactly one place
that knows where the database lives.
"""

from __future__ import annotations

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from dealsignal import models  # noqa: F401  - imported so autogenerate sees every table
from dealsignal.core.config import get_settings
from dealsignal.db.base import Base

config = context.config
config.set_main_option("sqlalchemy.url", str(get_settings().database_url))

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

# PostGIS puts its own tables (spatial_ref_sys, the tiger geocoder) on the search
# path, so autogenerate sees them as ours and writes migrations that drop them.
# The rule is simple: migrations manage only the tables this application declares.
# Dropping a table therefore needs a hand-written migration, which is the safer
# default anyway.


def include_object(
    obj: object, name: str | None, type_: str, reflected: bool, compare_to: object
) -> bool:
    """True only for tables and indexes belonging to our own models."""
    if type_ == "table":
        return name in target_metadata.tables
    if type_ == "index":
        table_name = getattr(getattr(obj, "table", None), "name", None)
        return table_name in target_metadata.tables
    return True


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        compare_type=True,
        include_object=include_object,
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        include_object=include_object,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    engine = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with engine.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
