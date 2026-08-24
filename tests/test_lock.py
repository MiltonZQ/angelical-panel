"""Covers lock_sesion()/unlock_sesion() -- the per-phone execution lock
backing POST /api/sesion/lock and /api/sesion/unlock.

Acquisition is one atomic INSERT ... ON CONFLICT DO UPDATE ... WHERE
statement: there is no separate acquire/expire round trip to race, so these
tests exercise the SQL directly against a real Postgres database rather than
mocking the pool.
"""

from app.db import SESION_LOCK_TTL, lock_sesion, unlock_sesion

TELEFONO = "3007770001"


async def test_lock_acquired_when_free(pg_pool):
    adquirido = await lock_sesion(pg_pool, TELEFONO, "run-a")

    assert adquirido is True
    fila = await pg_pool.fetchrow(
        "SELECT ejecucion, expira_at > now() AS vigente FROM sesiones_bot_angelical WHERE telefono=$1",
        TELEFONO,
    )
    assert fila["ejecucion"] == "run-a"
    assert fila["vigente"] is True


async def test_lock_contended_by_a_second_live_execution(pg_pool):
    primero = await lock_sesion(pg_pool, TELEFONO, "run-a")
    segundo = await lock_sesion(pg_pool, TELEFONO, "run-b")

    assert primero is True
    assert segundo is False
    # The row still belongs to the first execution -- contention must not
    # overwrite the holder.
    fila = await pg_pool.fetchrow(
        "SELECT ejecucion FROM sesiones_bot_angelical WHERE telefono=$1", TELEFONO
    )
    assert fila["ejecucion"] == "run-a"


async def test_lock_reacquired_after_expiry(pg_pool):
    await lock_sesion(pg_pool, TELEFONO, "run-a")
    # Force the existing lock into the past -- simulates the holder crashing
    # and the TTL elapsing, without waiting SESION_LOCK_TTL seconds in the
    # test itself.
    await pg_pool.execute(
        "UPDATE sesiones_bot_angelical SET expira_at = now() - interval '1 second' WHERE telefono=$1",
        TELEFONO,
    )

    segundo = await lock_sesion(pg_pool, TELEFONO, "run-b")

    assert segundo is True
    fila = await pg_pool.fetchrow(
        "SELECT ejecucion, expira_at > now() AS vigente FROM sesiones_bot_angelical WHERE telefono=$1",
        TELEFONO,
    )
    assert fila["ejecucion"] == "run-b"
    assert fila["vigente"] is True


async def test_unlock_releases_a_matching_execution(pg_pool):
    await lock_sesion(pg_pool, TELEFONO, "run-a")

    liberado = await unlock_sesion(pg_pool, TELEFONO, "run-a")

    assert liberado is True
    fila = await pg_pool.fetchrow(
        "SELECT 1 FROM sesiones_bot_angelical WHERE telefono=$1", TELEFONO
    )
    assert fila is None
    # The lock is free again for a brand-new execution.
    assert await lock_sesion(pg_pool, TELEFONO, "run-c") is True


async def test_unlock_with_foreign_ejecucion_does_not_release(pg_pool):
    """The exact scenario the design calls out: one run must never release
    another run's lock."""
    await lock_sesion(pg_pool, TELEFONO, "run-a")

    liberado = await unlock_sesion(pg_pool, TELEFONO, "run-b-not-the-holder")

    assert liberado is False
    fila = await pg_pool.fetchrow(
        "SELECT ejecucion, expira_at > now() AS vigente FROM sesiones_bot_angelical WHERE telefono=$1",
        TELEFONO,
    )
    assert fila is not None, "the real holder's row must still exist"
    assert fila["ejecucion"] == "run-a"
    assert fila["vigente"] is True


async def test_unlock_on_a_phone_with_no_lock_is_a_harmless_no_op(pg_pool):
    liberado = await unlock_sesion(pg_pool, "3007770099", "run-nonexistent")

    assert liberado is False


def test_lock_ttl_matches_the_documented_180_seconds():
    assert SESION_LOCK_TTL == 180
