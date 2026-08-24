"""Covers reconciliar_reservas() -- the hourly sweep (POST /api/reconciliar).

Two distinct behaviors, kept separate on purpose:
  1. Confirmed active rows whose Cal.com booking is gone (UI-side
     cancellation) get closed as 'cancelada_externa'. A row whose Cal.com
     booking still exists MUST be left alone.
  2. Stale pending rows (process died between T1 and T2) get adopted or
     expired -- same adopt-or-expire rule as expirar_pendientes(), applied
     across every pair instead of one.
"""

from app.db import RESERVA_PENDIENTE_TTL, confirmar_reserva, insert_reserva, reconciliar_reservas

FECHA = "2026-09-01"
HORA = "09:00"


async def _no_reserva_cal(cal_uid):
    raise AssertionError("no confirmed rows in this test -- must not be called")


async def _no_cal_uid(stale_row):
    raise AssertionError("no pending rows in this test -- must not be called")


async def _insert_confirmada(pg_pool, telefono, paciente, cal_uid):
    reserva = await insert_reserva(pg_pool, telefono, paciente, FECHA, HORA)
    await confirmar_reserva(pg_pool, reserva["id"], cal_uid)
    return reserva


async def _insert_stale_pending(pg_pool, telefono, paciente, seconds_old=RESERVA_PENDIENTE_TTL + 30):
    reserva = await insert_reserva(pg_pool, telefono, paciente, FECHA, HORA)
    await pg_pool.execute(
        "UPDATE reservas_primera_angelical SET created_at = now() - ($1 || ' seconds')::interval WHERE id=$2",
        str(seconds_old), reserva["id"],
    )
    return reserva


async def test_confirmed_row_closed_when_cal_booking_gone(pg_pool):
    reserva = await _insert_confirmada(pg_pool, "3006660001", "Paciente Drift", "cal-uid-borrado")

    async def buscar_reserva_cal_ausente(cal_uid):
        assert cal_uid == "cal-uid-borrado"
        return None

    resultado = await reconciliar_reservas(pg_pool, buscar_reserva_cal_ausente, _no_cal_uid)

    assert resultado == {"revisadas": 1, "cerradas": 1, "adoptadas": 0, "expiradas": 0}
    fila = await pg_pool.fetchrow(
        "SELECT estado, motivo_cierre FROM reservas_primera_angelical WHERE id=$1", reserva["id"]
    )
    assert fila["estado"] == "cancelada_externa"
    assert fila["motivo_cierre"] == "reconcile_hourly"


async def test_confirmed_row_left_alone_when_cal_booking_still_active(pg_pool):
    reserva = await _insert_confirmada(pg_pool, "3006660002", "Paciente Vigente", "cal-uid-vigente")

    async def buscar_reserva_cal_presente(cal_uid):
        assert cal_uid == "cal-uid-vigente"
        return {"uid": cal_uid, "status": "accepted"}

    resultado = await reconciliar_reservas(pg_pool, buscar_reserva_cal_presente, _no_cal_uid)

    assert resultado == {"revisadas": 1, "cerradas": 0, "adoptadas": 0, "expiradas": 0}
    fila = await pg_pool.fetchrow(
        "SELECT estado, motivo_cierre FROM reservas_primera_angelical WHERE id=$1", reserva["id"]
    )
    assert fila["estado"] == "activa"
    assert fila["motivo_cierre"] is None


async def test_stale_pending_adopted_during_reconcile(pg_pool):
    reserva = await _insert_stale_pending(pg_pool, "3006660003", "Paciente Adopta Reconcile")

    async def buscar_cal_uid_encontrado(stale_row):
        assert stale_row["id"] == reserva["id"]
        return "cal-uid-adoptado-reconcile"

    resultado = await reconciliar_reservas(pg_pool, _no_reserva_cal, buscar_cal_uid_encontrado)

    assert resultado == {"revisadas": 1, "cerradas": 0, "adoptadas": 1, "expiradas": 0}
    fila = await pg_pool.fetchrow(
        "SELECT estado, cal_uid, confirmed_at FROM reservas_primera_angelical WHERE id=$1", reserva["id"]
    )
    assert fila["estado"] == "activa"
    assert fila["cal_uid"] == "cal-uid-adoptado-reconcile"
    assert fila["confirmed_at"] is not None


async def test_stale_pending_expired_during_reconcile(pg_pool):
    reserva = await _insert_stale_pending(pg_pool, "3006660004", "Paciente Expira Reconcile")

    async def buscar_cal_uid_ausente(stale_row):
        assert stale_row["id"] == reserva["id"]
        return None

    resultado = await reconciliar_reservas(pg_pool, _no_reserva_cal, buscar_cal_uid_ausente)

    assert resultado == {"revisadas": 1, "cerradas": 0, "adoptadas": 0, "expiradas": 1}
    fila = await pg_pool.fetchrow(
        "SELECT estado, motivo_cierre, cal_uid FROM reservas_primera_angelical WHERE id=$1", reserva["id"]
    )
    assert fila["estado"] == "expirada"
    assert fila["motivo_cierre"] == "pending_ttl_sin_reserva_en_cal"
    assert fila["cal_uid"] is None


async def test_pending_row_younger_than_ttl_is_never_swept_by_reconcile(pg_pool):
    """Not stale yet -- reconcile must not touch it or call Cal.com for it."""
    reserva = await insert_reserva(pg_pool, "3006660005", "Paciente Fresco", FECHA, HORA)

    resultado = await reconciliar_reservas(pg_pool, _no_reserva_cal, _no_cal_uid)

    assert resultado == {"revisadas": 0, "cerradas": 0, "adoptadas": 0, "expiradas": 0}
    fila = await pg_pool.fetchrow("SELECT estado FROM reservas_primera_angelical WHERE id=$1", reserva["id"])
    assert fila["estado"] == "activa"
