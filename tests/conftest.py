"""Shared pytest fixtures for the panel test suite.

Every integration test in this suite runs against a REAL Postgres database
-- never sqlite, never a mocked pool. The concurrency and constraint tests
this change adds only prove anything if the actual `UNIQUE` index decides
the winner; a mock cannot exercise that.

Preferred: `testcontainers[postgresql]` spins up an ephemeral, hermetic
Postgres container per test session -- no local setup required beyond
Docker.

Fallback: when Docker is unavailable, set `TEST_DATABASE_URL` to point at a
scratch Postgres database (e.g. a local `createdb angelical_panel_test`) and
the suite uses that instead. This is the documented fallback from the SDD
design and tasks for this change; it was exercised directly in this
environment because Docker was not installed here.
"""

import os

import asyncpg
import pytest
import pytest_asyncio

_MIGRATIONS_DIR = os.path.join(os.path.dirname(__file__), "..", "migrations")


def _read_migration(filename: str) -> str:
    path = os.path.join(_MIGRATIONS_DIR, filename)
    with open(path, "r", encoding="utf-8") as fh:
        return fh.read()


@pytest.fixture(scope="session")
def database_url():
    """Yields a real Postgres connection string for the whole test session.

    Resolution order:
    1. `TEST_DATABASE_URL` env var, when set -- always wins, no container.
    2. `testcontainers[postgresql]`, when Docker is reachable.
    3. Skip the test session with a clear reason otherwise (never silently
       downgrade to sqlite or a mock).
    """
    env_url = os.getenv("TEST_DATABASE_URL")
    if env_url:
        yield env_url
        return

    try:
        from testcontainers.postgres import PostgresContainer
    except ImportError as exc:
        pytest.skip(
            "testcontainers is not installed and TEST_DATABASE_URL is not set "
            f"-- no real Postgres available for this test session ({exc})"
        )
        return

    try:
        with PostgresContainer("postgres:16-alpine") as container:
            yield container.get_connection_url().replace(
                "postgresql+psycopg2", "postgresql"
            )
    except Exception as exc:  # Docker daemon unreachable, image pull failed, etc.
        pytest.skip(
            "testcontainers could not start a Postgres container -- set "
            f"TEST_DATABASE_URL to a scratch Postgres instead ({exc})"
        )


@pytest_asyncio.fixture
async def pg_pool(database_url):
    """Fresh ledger schema per test: applies migration 001 ONLY, tears down
    after. This matches production through slice S2 -- migration 002 (the
    `ux_reserva_activa_paciente` unique index) is NOT applied here, exactly
    like it is not applied in production until slice S3's backfill gate.

    Scoped per-test (not per-session) so tests never leak rows into each
    other -- required for the concurrency/race assertions added in later
    slices, which count rows exactly.
    """
    pool = await asyncpg.create_pool(
        database_url, min_size=1, max_size=5, statement_cache_size=0
    )
    async with pool.acquire() as conn:
        await conn.execute(_read_migration("001_reservas_ledger.sql"))
    try:
        yield pool
    finally:
        async with pool.acquire() as conn:
            await conn.execute("DROP TABLE IF EXISTS sesiones_bot_angelical")
            await conn.execute("DROP TABLE IF EXISTS reservas_primera_angelical")
        await pool.close()


@pytest_asyncio.fixture
async def pg_pool_enforced(database_url):
    """Ledger schema with 001 + 002 applied -- the ONLY place migration 002
    is ever executed in this slice. Test-only: it exists so
    `tests/test_concurrency.py` and `tests/test_cal_ordering.py` can exercise
    the real `ux_reserva_activa_paciente` constraint that
    `validar_y_agendar()`'s `UniqueViolationError` handling depends on, even
    though production does not have that index until slice S3. This fixture
    must NEVER be pointed at a production or staging database.
    """
    pool = await asyncpg.create_pool(
        database_url, min_size=2, max_size=5, statement_cache_size=0
    )
    async with pool.acquire() as conn:
        await conn.execute(_read_migration("001_reservas_ledger.sql"))
        await conn.execute(_read_migration("002_unique_activa.sql"))
    try:
        yield pool
    finally:
        async with pool.acquire() as conn:
            await conn.execute("DROP TABLE IF EXISTS sesiones_bot_angelical")
            await conn.execute("DROP TABLE IF EXISTS reservas_primera_angelical")
        await pool.close()
