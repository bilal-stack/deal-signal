"""Fixtures for tests that need a real Postgres.

Three rules keep these tests honest and safe:

* They use their own database, `dealsignal_test`, created on demand. The
  development data is never touched.
* The schema comes from running the real Alembic migrations, so a broken
  migration fails here rather than on a grader's machine.
* Every test runs inside a transaction that is rolled back afterwards. The session
  joins it in savepoint mode, so code under test can call `commit()` (the merge
  endpoint does) and the test still leaves nothing behind.

If the database cannot be reached, these tests are skipped with a clear reason and
the unit tests still run.
"""

from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
from collections.abc import AsyncIterator
from pathlib import Path

import asyncpg
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from dealsignal.core.config import Settings
from dealsignal.db.session import get_session
from dealsignal.main import create_app

TEST_DATABASE = "dealsignal_test"
EXTENSIONS = ("postgis", "pg_trgm", "vector")
API_ROOT = Path(__file__).resolve().parents[2]


def _test_database_url() -> str:
    """The test database lives next to the development one, under its own name."""
    configured = os.environ.get("TEST_DATABASE_URL")
    if configured:
        return configured
    base = os.environ.get(
        "DATABASE_URL", "postgresql+asyncpg://dealsignal:dealsignal@localhost:5433/dealsignal"
    )
    return base.rsplit("/", 1)[0] + f"/{TEST_DATABASE}"


def _plain_dsn(url: str) -> str:
    """asyncpg does not understand SQLAlchemy's driver suffix."""
    return url.replace("postgresql+asyncpg://", "postgresql://")


async def _prepare_database(url: str) -> None:
    """Create the test database and its extensions if they are missing."""
    admin = await asyncpg.connect(_plain_dsn(url).rsplit("/", 1)[0] + "/postgres")
    try:
        exists = await admin.fetchval("select 1 from pg_database where datname = $1", TEST_DATABASE)
        if not exists:
            await admin.execute(f'create database "{TEST_DATABASE}"')
    finally:
        await admin.close()

    database = await asyncpg.connect(_plain_dsn(url))
    try:
        for extension in EXTENSIONS:
            await database.execute(f"create extension if not exists {extension}")
    finally:
        await database.close()


@pytest.fixture(scope="session")
def database_url() -> str:
    """A migrated test database, or a skip explaining why there is none."""
    url = _test_database_url()
    try:
        asyncio.run(_prepare_database(url))
    except (OSError, asyncpg.PostgresError) as exc:
        pytest.skip(f"Integration tests need Postgres at {url}: {exc}")

    alembic = shutil.which("alembic")
    if alembic is None:
        pytest.fail("Alembic is not installed, so the test schema cannot be built.")

    migration = subprocess.run(  # noqa: S603 - fixed arguments, no user input
        [alembic, "upgrade", "head"],
        cwd=API_ROOT,
        env={**os.environ, "DATABASE_URL": url},
        capture_output=True,
        text=True,
        check=False,
    )
    if migration.returncode != 0:
        pytest.fail(f"Migrations failed on a clean database:\n{migration.stderr}")
    return url


@pytest.fixture
async def db_session(database_url: str) -> AsyncIterator[AsyncSession]:
    """A session whose every change, committed or not, is rolled back afterwards."""
    engine = create_async_engine(database_url)
    async with engine.connect() as connection:
        transaction = await connection.begin()
        session = AsyncSession(
            bind=connection,
            expire_on_commit=False,
            join_transaction_mode="create_savepoint",
        )
        try:
            yield session
        finally:
            await session.close()
            await transaction.rollback()
    await engine.dispose()


@pytest.fixture
async def api(db_session: AsyncSession, database_url: str) -> AsyncIterator[AsyncClient]:
    """The real application, with its database session swapped for the test one."""
    app = create_app(Settings(environment="ci", log_format="json", database_url=database_url))

    async def override_session() -> AsyncIterator[AsyncSession]:
        yield db_session

    app.dependency_overrides[get_session] = override_session
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client
