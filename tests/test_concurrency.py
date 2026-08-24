"""Proves the race is closed by the real Postgres constraint, not luck.

Real Postgres only (pg_pool_enforced applies 001 + 002). Two distinct pool
connections, asyncio.Barrier(2) immediately before each INSERT so both are
genuinely in flight, asyncio.gather. Never sqlite, never a mocked pool.
"""

import asyncio

import asyncpg
import pytest

from app.db import insert_reserva

FECHA = "2026-09-01"
HORA = "09:00"


async def _racing_insert(pool, barrier, telefono, paciente):
    async with pool.acquire() as conn:
        await barrier.wait()
        try:
            return ("ok", await insert_reserva(conn, telefono, paciente, FECHA, HORA))
        except asyncpg.exceptions.UniqueViolationError as e:
            return ("violation", e)


@pytest.mark.parametrize("intento", range(25))
async def test_exactly_one_insert_wins_the_race(pg_pool_enforced, intento):
    """Repeated x25 to defeat scheduling luck, per design."""
    barrier = asyncio.Barrier(2)
    telefono, paciente = "3005551234", f"Paciente Carrera {intento}"

    resultados = await asyncio.gather(
        _racing_insert(pg_pool_enforced, barrier, telefono, paciente),
        _racing_insert(pg_pool_enforced, barrier, telefono, paciente),
    )

    kinds = sorted(kind for kind, _ in resultados)
    assert kinds == ["ok", "violation"], f"expected one winner + one violation, got {kinds}"
    loser_error = next(err for kind, err in resultados if kind == "violation")
    assert loser_error.constraint_name == "ux_reserva_activa_paciente"


async def test_fast_loser_returns_in_under_100ms(pg_pool_enforced):
    """pg_sleep variant: a "winner" commits its INSERT then sleeps 2s
    (stand-in for crear_reserva()'s HTTP call happening AFTER T1 commits,
    per the two-transaction design). A genuinely racing loser INSERT
    against the SAME pair must be rejected near-instantly by the unique
    index -- not block for anywhere close to the winner's 2s. This is the
    direct proof that T1 is never held open across slow work."""
    telefono, paciente = "3005558888", "Paciente Cronometrado"

    async def winner_committed_then_slow():
        async with pg_pool_enforced.acquire() as conn:
            await insert_reserva(conn, telefono, paciente, FECHA, HORA)
            await conn.execute("SELECT pg_sleep(2)")

    winner_task = asyncio.create_task(winner_committed_then_slow())
    await asyncio.sleep(0.3)  # let the winner actually commit first

    loop = asyncio.get_event_loop()
    start = loop.time()
    async with pg_pool_enforced.acquire() as loser_conn:
        with pytest.raises(asyncpg.exceptions.UniqueViolationError) as excinfo:
            await asyncio.wait_for(
                insert_reserva(loser_conn, telefono, paciente, FECHA, HORA), timeout=1.0
            )
    elapsed = loop.time() - start
    await winner_task

    assert excinfo.value.constraint_name == "ux_reserva_activa_paciente"
    assert elapsed < 0.1, f"loser took {elapsed:.3f}s, expected <100ms"
