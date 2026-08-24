"""Regression guard: ledger INSERT (T1) must commit before Cal.com's
POST /v2/bookings -- never a shared transaction across the HTTP call. Also
covers T2 compensation on Cal.com failure and the on-read self-heal path.
"""

import asyncpg
import pytest
import respx
from httpx import Response

from app import cal
from app.db import confirmar_reserva, insert_reserva

FECHA = "2026-09-01"  # Tuesday, valid appointment weekday, no holiday.
HORA = "09:00"


def _mock_cal_endpoints(router: respx.MockRouter, *, booking_status=201, booking_uid="uid-123"):
    router.get("https://api.cal.com/v2/bookings", params={"eventTypeId": cal.config.CAL_EVENT_TYPE_ID}) \
        .mock(return_value=Response(200, json={"data": []}))
    router.get("https://api.cal.com/v2/slots").mock(
        return_value=Response(
            200, json={"data": {f"{FECHA}T14:00:00.000Z": [{"start": f"{FECHA}T14:00:00.000Z"}]}}
        )
    )
    booking_json = {"data": {"uid": booking_uid, "status": "accepted"}} if booking_status in (200, 201) else {"error": "boom"}
    router.post("https://api.cal.com/v2/bookings").mock(return_value=Response(booking_status, json=booking_json))


async def _fake_get_pool(pool):
    return pool


async def test_ledger_insert_precedes_cal_booking_post(pg_pool, monkeypatch):
    """The actual regression guard: recorded call order must be
    ledger_insert -> cal_booking_post, never the reverse."""
    orden = []
    monkeypatch.setattr(cal, "get_pool", lambda: _fake_get_pool(pg_pool))
    real_insert = cal.insert_reserva

    async def insert_recorder(pool, *args, **kwargs):
        orden.append("ledger_insert")
        return await real_insert(pool, *args, **kwargs)

    monkeypatch.setattr(cal, "insert_reserva", insert_recorder)

    with respx.mock(assert_all_called=False) as router:
        _mock_cal_endpoints(router)

        async def post_recorder(request):
            orden.append("cal_booking_post")
            return Response(201, json={"data": {"uid": "uid-123", "status": "accepted"}})

        router.post("https://api.cal.com/v2/bookings").mock(side_effect=post_recorder)
        resultado = await cal.validar_y_agendar("Paciente Orden", "p@example.com", "3001234567", FECHA, HORA)

    assert resultado["ok"] is True
    assert orden == ["ledger_insert", "cal_booking_post"], orden


async def test_cal_com_failure_compensates_without_rollback(pg_pool, monkeypatch):
    """T2 failure closes the ledger row as 'fallida' -- never deletes or
    rolls back the T1 insert; the row stays for audit."""
    monkeypatch.setattr(cal, "get_pool", lambda: _fake_get_pool(pg_pool))
    with respx.mock(assert_all_called=False) as router:
        _mock_cal_endpoints(router, booking_status=500)
        resultado = await cal.validar_y_agendar("Paciente Falla", "f@example.com", "3009999999", FECHA, HORA)

    assert resultado["ok"] is False
    fila = await pg_pool.fetchrow(
        "SELECT estado, motivo_cierre FROM reservas_primera_angelical WHERE paciente=$1", "Paciente Falla"
    )
    assert fila is not None, "T1 insert must survive even when Cal.com fails"
    assert fila["estado"] == "fallida"
    assert fila["motivo_cierre"] == "cal_error"


async def test_rejection_self_heals_when_blocking_booking_was_cancelled_externally(pg_pool_enforced, monkeypatch):
    """The blocking row's Cal.com booking was cancelled in the Cal.com UI.
    On-read reconcile must verify it BEFORE returning the rejection,
    self-heal (estado='cancelada_externa') and retry the insert once."""
    telefono, paciente = "3005557777", "Paciente Autosana"
    bloqueante = await insert_reserva(pg_pool_enforced, telefono, paciente, FECHA, HORA)
    await confirmar_reserva(pg_pool_enforced, bloqueante["id"], "uid-cancelado-en-cal")
    monkeypatch.setattr(cal, "get_pool", lambda: _fake_get_pool(pg_pool_enforced))

    with respx.mock(assert_all_called=False) as router:
        _mock_cal_endpoints(router, booking_uid="uid-nuevo-tras-autosana")
        router.get("https://api.cal.com/v2/bookings/uid-cancelado-en-cal").mock(
            return_value=Response(404, json={"error": "not found"})
        )
        resultado = await cal.validar_y_agendar(paciente, "a@example.com", telefono, FECHA, HORA)

    assert resultado["ok"] is True, resultado
    assert resultado["uid"] == "uid-nuevo-tras-autosana"
    vieja, nueva = await pg_pool_enforced.fetch(
        "SELECT estado, cal_uid, motivo_cierre FROM reservas_primera_angelical WHERE telefono=$1 ORDER BY id",
        telefono,
    )
    assert vieja["estado"] == "cancelada_externa"
    assert vieja["motivo_cierre"] == "cal_uid_cancelado_reconcile"
    assert nueva["estado"] == "activa"
    assert nueva["cal_uid"] == "uid-nuevo-tras-autosana"


async def test_rejection_stays_rejected_when_blocking_booking_still_active(pg_pool_enforced, monkeypatch):
    """Mirror case: the blocking booking is still live in Cal.com -- no
    self-heal, real rejection, runnable continuation in the message."""
    telefono, paciente = "3005556666", "Paciente Bloqueado"
    bloqueante = await insert_reserva(pg_pool_enforced, telefono, paciente, FECHA, HORA)
    await confirmar_reserva(pg_pool_enforced, bloqueante["id"], "uid-todavia-activo")
    monkeypatch.setattr(cal, "get_pool", lambda: _fake_get_pool(pg_pool_enforced))

    with respx.mock(assert_all_called=False) as router:
        _mock_cal_endpoints(router)
        router.get("https://api.cal.com/v2/bookings/uid-todavia-activo").mock(
            return_value=Response(200, json={"data": {"uid": "uid-todavia-activo", "status": "accepted"}})
        )
        resultado = await cal.validar_y_agendar(paciente, "b@example.com", telefono, FECHA, HORA)

    assert resultado["ok"] is False
    assert "ya tiene una primera consulta activa" in resultado["error"]
    assert "cancela la actual primero" in resultado["error"]
    filas = await pg_pool_enforced.fetch("SELECT estado FROM reservas_primera_angelical WHERE telefono=$1", telefono)
    assert len(filas) == 1 and filas[0]["estado"] == "activa"


async def test_unrelated_unique_violation_is_never_swallowed(pg_pool, monkeypatch):
    """Match constraint_name == 'ux_reserva_activa_paciente' specifically --
    a violation on a DIFFERENT constraint is a real fault and must
    propagate, never be silently treated as a duplicate booking."""
    monkeypatch.setattr(cal, "get_pool", lambda: _fake_get_pool(pg_pool))

    async def insert_raises_wrong_constraint(pool, *args, **kwargs):
        err = asyncpg.exceptions.UniqueViolationError("simulated unrelated violation")
        err.constraint_name = "ux_reserva_cal_uid"
        raise err

    monkeypatch.setattr(cal, "insert_reserva", insert_raises_wrong_constraint)

    with respx.mock(assert_all_called=False) as router:
        _mock_cal_endpoints(router)
        with pytest.raises(asyncpg.exceptions.UniqueViolationError) as excinfo:
            await cal.validar_y_agendar("Paciente No Relacionado", "n@example.com", "3005550099", FECHA, HORA)

    assert excinfo.value.constraint_name == "ux_reserva_cal_uid"
