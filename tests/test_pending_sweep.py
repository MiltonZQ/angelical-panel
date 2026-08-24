"""Covers BOTH paths of expirar_pendientes() explicitly.

Blind expiry is the sharpest risk in the whole change: a process that died
AFTER Cal.com confirmed the booking (but before confirmar_reserva() stamped
it) must ADOPT the row, not expire it -- expiring would let a second insert
through and produce a real double booking. Not found in Cal.com -> expired.
"""

from app.db import RESERVA_PENDIENTE_TTL, expirar_pendientes, insert_reserva

FECHA = "2026-09-01"
HORA = "09:00"


async def _insert_stale_pending(pg_pool, telefono, paciente, seconds_old):
    reserva = await insert_reserva(pg_pool, telefono, paciente, FECHA, HORA)
    await pg_pool.execute(
        "UPDATE reservas_primera_angelical SET created_at = now() - ($1 || ' seconds')::interval WHERE id=$2",
        str(seconds_old), reserva["id"],
    )
    return reserva


async def test_stale_pending_adopted_when_cal_booking_found(pg_pool):
    telefono, paciente = "3005550001", "Paciente Adoptado"
    reserva = await _insert_stale_pending(pg_pool, telefono, paciente, RESERVA_PENDIENTE_TTL + 30)

    async def buscar_cal_uid_encontrado(stale_row):
        assert stale_row["id"] == reserva["id"]
        return "cal-uid-adoptado-999"

    resultado = await expirar_pendientes(
        pg_pool, reserva["telefono_norm"], reserva["paciente_norm"], buscar_cal_uid_encontrado
    )

    assert resultado == "cal-uid-adoptado-999"
    fila = await pg_pool.fetchrow(
        "SELECT estado, cal_uid, confirmed_at FROM reservas_primera_angelical WHERE id=$1", reserva["id"]
    )
    assert fila["estado"] == "activa"
    assert fila["cal_uid"] == "cal-uid-adoptado-999"
    assert fila["confirmed_at"] is not None


async def test_stale_pending_expired_when_cal_booking_not_found(pg_pool):
    telefono, paciente = "3005550002", "Paciente Expirado"
    reserva = await _insert_stale_pending(pg_pool, telefono, paciente, RESERVA_PENDIENTE_TTL + 30)

    async def buscar_cal_uid_ausente(stale_row):
        assert stale_row["id"] == reserva["id"]
        return None

    resultado = await expirar_pendientes(
        pg_pool, reserva["telefono_norm"], reserva["paciente_norm"], buscar_cal_uid_ausente
    )

    assert resultado is None
    fila = await pg_pool.fetchrow(
        "SELECT estado, motivo_cierre, cal_uid FROM reservas_primera_angelical WHERE id=$1", reserva["id"]
    )
    assert fila["estado"] == "expirada"
    assert fila["motivo_cierre"] == "pending_ttl_sin_reserva_en_cal"
    assert fila["cal_uid"] is None


async def test_pending_row_younger_than_ttl_is_left_alone(pg_pool):
    """Not stale yet -- the sweep must not touch it or call Cal.com."""
    telefono, paciente = "3005550003", "Paciente En Vuelo"
    reserva = await insert_reserva(pg_pool, telefono, paciente, FECHA, HORA)
    llamado = False

    async def buscar_cal_uid_no_deberia_llamarse(stale_row):
        nonlocal llamado
        llamado = True
        return None

    resultado = await expirar_pendientes(
        pg_pool, reserva["telefono_norm"], reserva["paciente_norm"], buscar_cal_uid_no_deberia_llamarse
    )

    assert resultado is None and llamado is False
    fila = await pg_pool.fetchrow("SELECT estado FROM reservas_primera_angelical WHERE id=$1", reserva["id"])
    assert fila["estado"] == "activa"


async def test_confirmed_active_row_is_never_swept(pg_pool):
    """A confirmed booking is never a sweep target, no matter how old --
    the sweep only ever targets confirmed_at IS NULL rows."""
    telefono, paciente = "3005550004", "Paciente Confirmado"
    reserva = await insert_reserva(pg_pool, telefono, paciente, FECHA, HORA)
    await pg_pool.execute(
        "UPDATE reservas_primera_angelical SET confirmed_at=now(), cal_uid=$1, "
        "created_at = now() - ($2 || ' seconds')::interval WHERE id=$3",
        "cal-uid-ya-confirmado", str(RESERVA_PENDIENTE_TTL + 999), reserva["id"],
    )
    llamado = False

    async def buscar_cal_uid_no_deberia_llamarse(stale_row):
        nonlocal llamado
        llamado = True
        return None

    resultado = await expirar_pendientes(
        pg_pool, reserva["telefono_norm"], reserva["paciente_norm"], buscar_cal_uid_no_deberia_llamarse
    )

    assert resultado is None and llamado is False
