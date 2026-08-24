"""Capa Cal.com para PRIMERA CONSULTA con las reglas de la fundación aplicadas en código.

El bot de WhatsApp no puede saltarse estas reglas: no ve Cal.com directamente, solo estos
helpers. Reglas aplicadas aquí (no en el prompt):

  - Solo días de atención (martes, miércoles, viernes, sábado), sin festivos ni vacaciones
    → reutiliza is_valid_appointment_date() de app/db.py
  - Solo horas entre CAL_PRIMER_SLOT y CAL_ULTIMO_SLOT (09:00–11:00). El 11:30 queda fuera.
  - Máximo CAL_MAX_CITAS_DIA (4) primeras consultas por día.
  - Todo se devuelve ya en hora de Colombia: el bot nunca vuelve a convertir de UTC.
"""

import logging
from datetime import date as dt_date, datetime, time as dt_time, timedelta
from zoneinfo import ZoneInfo

import asyncpg
import httpx

from app import config
from app.db import (
    buscar_activa,
    cerrar_reserva,
    confirmar_reserva,
    expirar_pendientes,
    get_pool,
    insert_reserva,
    invalid_date_error,
    is_valid_appointment_date,
)
from app.normalize import normalizar_identidad, normalizar_telefono

logger = logging.getLogger("uvicorn.error")

_TZ = ZoneInfo(config.BOT_TIMEZONE)
_UTC = ZoneInfo("UTC")

_DIAS_ES = {
    1: "lunes", 2: "martes", 3: "miércoles", 4: "jueves",
    5: "viernes", 6: "sábado", 7: "domingo",
}


def dia_semana(fecha: str) -> str:
    return _DIAS_ES[dt_date.fromisoformat(fecha).isoweekday()]


def horas_permitidas() -> list[str]:
    """Slots teóricos del día, de 30 min, entre el primero y el último permitidos."""
    inicio = dt_time.fromisoformat(config.CAL_PRIMER_SLOT)
    fin = dt_time.fromisoformat(config.CAL_ULTIMO_SLOT)
    base = datetime(2026, 1, 1, inicio.hour, inicio.minute)
    tope = datetime(2026, 1, 1, fin.hour, fin.minute)
    horas = []
    while base <= tope:
        horas.append(base.strftime("%H:%M"))
        base += timedelta(minutes=30)
    return horas


def _a_hora_local(iso_utc: str) -> tuple[str, str]:
    """'2026-08-25T14:00:00.000Z' -> ('2026-08-25', '09:00') en hora de Colombia."""
    dt = datetime.fromisoformat(iso_utc.replace("Z", "+00:00")).astimezone(_TZ)
    return dt.strftime("%Y-%m-%d"), dt.strftime("%H:%M")


def _a_iso_utc(fecha: str, hora: str) -> str:
    """('2026-08-25', '09:00') hora Colombia -> '2026-08-25T14:00:00Z'."""
    local = datetime.combine(
        dt_date.fromisoformat(fecha), dt_time.fromisoformat(hora), tzinfo=_TZ
    )
    return local.astimezone(_UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


async def citas_por_dia(desde: str, hasta: str) -> dict[str, int]:
    """Cuenta primeras consultas NO canceladas por fecha local, entre desde y hasta."""
    inicio = dt_date.fromisoformat(desde) - timedelta(days=1)
    fin = dt_date.fromisoformat(hasta) + timedelta(days=1)
    params = {
        "eventTypeId": config.CAL_EVENT_TYPE_ID,
        "afterStart": f"{inicio.isoformat()}T00:00:00Z",
        "beforeEnd": f"{fin.isoformat()}T00:00:00Z",
        "take": 250,
    }
    headers = {
        "cal-api-version": config.CAL_API_VERSION_BOOKINGS,
        "Authorization": f"Bearer {config.CAL_API_KEY}",
    }
    conteo: dict[str, int] = {}
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.get(
            "https://api.cal.com/v2/bookings", params=params, headers=headers
        )
        resp.raise_for_status()
        for b in resp.json().get("data", []) or []:
            if b.get("status") in ("cancelled", "rejected"):
                continue
            fecha, _ = _a_hora_local(b["start"])
            conteo[fecha] = conteo.get(fecha, 0) + 1
    return conteo


async def slots_disponibles(desde: str, hasta: str) -> dict[str, list[str]]:
    """Slots realmente reservables, en hora de Colombia, con TODAS las reglas aplicadas.

    Devuelve {'2026-08-25': ['09:00', '09:30'], ...} — solo días con cupo.
    """
    params = {
        "start": desde,
        "end": hasta,
        "username": config.CAL_USERNAME,
        "eventTypeSlug": config.CAL_EVENT_SLUG,
    }
    headers = {"cal-api-version": config.CAL_API_VERSION_SLOTS}
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.get(
            "https://api.cal.com/v2/slots", params=params, headers=headers
        )
        resp.raise_for_status()
        data = resp.json()

    crudos = data.get("data", data) if isinstance(data, dict) else {}
    if not isinstance(crudos, dict):
        crudos = {}

    permitidas = set(horas_permitidas())
    por_dia: dict[str, list[str]] = {}
    for _dia_utc, slots in crudos.items():
        for s in slots or []:
            inicio = s.get("start") if isinstance(s, dict) else s
            if not inicio:
                continue
            fecha, hora = _a_hora_local(inicio)
            # Regla: día de atención (no festivo, no vacaciones, no jueves/lunes/domingo)
            if not is_valid_appointment_date(fecha):
                continue
            # Regla: solo 09:00–11:00. Corta el 11:30 aunque Cal.com lo ofrezca.
            if hora not in permitidas:
                continue
            por_dia.setdefault(fecha, []).append(hora)

    if not por_dia:
        return {}

    # Regla: máximo 4 primeras consultas por día.
    ocupacion = await citas_por_dia(min(por_dia), max(por_dia))
    return {
        fecha: sorted(set(horas))
        for fecha, horas in sorted(por_dia.items())
        if ocupacion.get(fecha, 0) < config.CAL_MAX_CITAS_DIA
    }


async def crear_reserva(
    nombre: str, email: str, telefono: str, fecha: str, hora: str, motivo: str = ""
) -> dict:
    """POST a Cal.com. Solo devuelve ok=True si Cal.com respondió con un uid real."""
    headers = {
        "cal-api-version": config.CAL_API_VERSION_BOOKINGS,
        "Authorization": f"Bearer {config.CAL_API_KEY}",
        "Content-Type": "application/json",
    }
    body = {
        "start": _a_iso_utc(fecha, hora),
        "attendee": {
            "name": nombre,
            "email": email,
            "phoneNumber": telefono,
            "timeZone": config.BOT_TIMEZONE,
        },
        "eventTypeSlug": config.CAL_EVENT_SLUG,
        "username": config.CAL_USERNAME,
        "metadata": {"motivo": motivo} if motivo else {},
    }
    async with httpx.AsyncClient(timeout=25) as client:
        resp = await client.post(
            "https://api.cal.com/v2/bookings", headers=headers, json=body
        )
        try:
            result = resp.json()
        except ValueError:
            result = {}

    datos = result.get("data") if isinstance(result.get("data"), dict) else result
    uid = datos.get("uid") if isinstance(datos, dict) else None
    if resp.status_code in (200, 201) and uid:
        return {"ok": True, "uid": uid, "fecha": fecha, "hora": hora}

    detalle = result.get("error") or result.get("message") or resp.text[:200]
    if isinstance(detalle, dict):
        detalle = detalle.get("message", str(detalle))
    logger.error(f"Cal.com rechazó la reserva {fecha} {hora}: {detalle}")
    return {"ok": False, "error": f"NO SE AGENDÓ: Cal.com rechazó la reserva ({detalle})"}


async def buscar_reserva_cal(uid: str) -> dict | None:
    """GET a single Cal.com booking by uid. Returns None when it is absent,
    cancelled, or rejected -- the "still really booked?" check used by the
    on-read reconcile path when the ledger rejects an insert."""
    headers = {
        "cal-api-version": config.CAL_API_VERSION_BOOKINGS,
        "Authorization": f"Bearer {config.CAL_API_KEY}",
    }
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.get(
            f"https://api.cal.com/v2/bookings/{uid}", headers=headers
        )
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        result = resp.json()
    datos = result.get("data") if isinstance(result.get("data"), dict) else result
    if not isinstance(datos, dict):
        return None
    if datos.get("status") in ("cancelled", "rejected"):
        return None
    return datos


async def _buscar_uid_pendiente(pendiente: dict) -> str | None:
    """Targeted Cal.com lookup used only by expirar_pendientes(): did a
    booking for this exact stale pending row actually get created, even
    though our process died before confirmar_reserva() could stamp it?
    Matches on attendee phone AND exact start time -- the (fecha, hora) the
    pending row was inserted with."""
    fecha = pendiente["fecha"].isoformat()
    hora = pendiente["hora"].strftime("%H:%M")
    objetivo = _a_iso_utc(fecha, hora)
    params = {
        "eventTypeId": config.CAL_EVENT_TYPE_ID,
        "afterStart": f"{fecha}T00:00:00Z",
        "beforeEnd": f"{(dt_date.fromisoformat(fecha) + timedelta(days=1)).isoformat()}T00:00:00Z",
        "take": 250,
    }
    headers = {
        "cal-api-version": config.CAL_API_VERSION_BOOKINGS,
        "Authorization": f"Bearer {config.CAL_API_KEY}",
    }
    telefono_objetivo = normalizar_telefono(pendiente["telefono"])
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.get(
            "https://api.cal.com/v2/bookings", params=params, headers=headers
        )
        resp.raise_for_status()
        for b in resp.json().get("data", []) or []:
            if b.get("status") in ("cancelled", "rejected"):
                continue
            if b.get("start") != objetivo:
                continue
            attendees = b.get("attendees") or [{}]
            telefono_attendee = (attendees[0] or {}).get("phoneNumber", "")
            if normalizar_telefono(telefono_attendee) == telefono_objetivo:
                return b.get("uid")
    return None


def _rechazo_duplicado(bloqueante: dict | None, paciente: str) -> dict:
    """Builds the existing `{"ok": False, "error": "NO SE AGENDÓ: ..."}` shape
    for a ledger-rejected duplicate. Names a runnable continuation, per
    design: cancel the current booking first, then book again."""
    if bloqueante is None:
        return {
            "ok": False,
            "error": (
                f"NO SE AGENDÓ: {paciente} ya tiene una primera consulta activa. "
                "Para cambiarla, cancela la actual primero y vuelve a agendar."
            ),
        }
    f = bloqueante["fecha"]
    f = f.isoformat() if hasattr(f, "isoformat") else f
    h = bloqueante["hora"]
    h = h.strftime("%H:%M") if hasattr(h, "strftime") else h
    return {
        "ok": False,
        "error": (
            f"NO SE AGENDÓ: {paciente} ya tiene una primera consulta activa el {f} "
            f"a las {h}. Para cambiarla, cancela la actual primero y vuelve a agendar."
        ),
    }


async def validar_y_agendar(
    nombre: str, email: str, telefono: str, fecha: str, hora: str, motivo: str = ""
) -> dict:
    """Puerta única de agendamiento. Cualquier violación aborta antes de tocar Cal.com."""
    if not nombre:
        return {"ok": False, "error": "NO SE AGENDÓ: falta el nombre del paciente."}
    if not fecha:
        return {"ok": False, "error": "NO SE AGENDÓ: falta la fecha (YYYY-MM-DD)."}
    if not hora:
        return {"ok": False, "error": "NO SE AGENDÓ: falta la hora (HH:MM)."}
    try:
        dt_date.fromisoformat(fecha)
        hora = dt_time.fromisoformat(hora).strftime("%H:%M")
    except (ValueError, TypeError):
        return {
            "ok": False,
            "error": "NO SE AGENDÓ: formato inválido. Usa fecha YYYY-MM-DD y hora HH:MM.",
        }

    if not is_valid_appointment_date(fecha):
        return {"ok": False, "error": f"NO SE AGENDÓ: {invalid_date_error(fecha)}"}

    if hora not in horas_permitidas():
        return {
            "ok": False,
            "error": (
                f"NO SE AGENDÓ: {hora} no es un horario de atención. "
                f"Solo {config.CAL_PRIMER_SLOT} a {config.CAL_ULTIMO_SLOT}."
            ),
        }

    try:
        ocupacion = await citas_por_dia(fecha, fecha)
    except Exception as e:
        logger.error(f"citas_por_dia falló para {fecha}: {e}")
        return {"ok": False, "error": "NO SE AGENDÓ: no se pudo verificar el cupo del día."}

    if ocupacion.get(fecha, 0) >= config.CAL_MAX_CITAS_DIA:
        return {
            "ok": False,
            "error": (
                f"NO SE AGENDÓ: el {fecha} ya tiene los {config.CAL_MAX_CITAS_DIA} cupos "
                "del día. Ofrece otra fecha consultando disponibilidad."
            ),
        }

    siguiente = (dt_date.fromisoformat(fecha) + timedelta(days=1)).isoformat()
    try:
        libres = (await slots_disponibles(fecha, siguiente)).get(fecha, [])
    except Exception as e:
        logger.error(f"slots_disponibles falló para {fecha}: {e}")
        return {"ok": False, "error": "NO SE AGENDÓ: no se pudo verificar la disponibilidad."}

    if hora not in libres:
        disponibles = ", ".join(libres) if libres else "ninguno"
        return {
            "ok": False,
            "error": (
                f"NO SE AGENDÓ: las {hora} del {fecha} no están disponibles. "
                f"Horarios libres ese día: {disponibles}."
            ),
        }

    # ── Ledger-first ordering (T1) ──────────────────────────────────────
    # From here on Postgres is the dedup authority, not another read-then-
    # write check. insert_reserva() (T1) commits immediately -- it is NOT
    # held open across the Cal.com HTTP call below (T1/T2 stay two separate
    # commits), otherwise the unique constraint would block the loser for
    # up to ~25s instead of rejecting it instantly, stalling the max_size=5
    # pool. See design decision "two transactions, not one open across the
    # Cal.com call".
    pool = await get_pool()
    telefono_norm = normalizar_telefono(telefono)
    paciente_norm = normalizar_identidad(nombre)

    await expirar_pendientes(pool, telefono_norm, paciente_norm, _buscar_uid_pendiente)

    try:
        reserva = await insert_reserva(pool, telefono, nombre, fecha, hora)
    except asyncpg.exceptions.UniqueViolationError as e:
        # Catch ONLY this specific constraint violation -- never a bare
        # `except Exception`, which would swallow real faults.
        if e.constraint_name != "ux_reserva_activa_paciente":
            raise
        bloqueante = await buscar_activa(pool, telefono_norm, paciente_norm)
        # On-read reconcile: before returning the rejection, verify the
        # blocking row's cal_uid is still live in Cal.com. Cancelled/absent
        # -> self-heal (mark cancelada_externa) and retry the insert once.
        if bloqueante and bloqueante.get("cal_uid"):
            vigente = await buscar_reserva_cal(bloqueante["cal_uid"])
            if vigente is None:
                await cerrar_reserva(
                    pool, bloqueante["id"], "cancelada_externa", "cal_uid_cancelado_reconcile"
                )
                try:
                    reserva = await insert_reserva(pool, telefono, nombre, fecha, hora)
                except asyncpg.exceptions.UniqueViolationError:
                    return _rechazo_duplicado(bloqueante, nombre)
            else:
                return _rechazo_duplicado(bloqueante, nombre)
        else:
            return _rechazo_duplicado(bloqueante, nombre)

    # T1 committed. crear_reserva() runs outside any transaction.
    resultado = await crear_reserva(nombre, email, telefono, fecha, hora, motivo)
    if resultado.get("ok"):
        # T2 success: stamp the Cal.com uid.
        await confirmar_reserva(pool, reserva["id"], resultado["uid"])
        return resultado

    # T2 failure: compensation, not rollback -- the ledger row stays for
    # audit, closed as 'fallida'.
    await cerrar_reserva(pool, reserva["id"], "fallida", "cal_error")
    return resultado


async def disponibilidad_para_bot(desde: str, hasta: str) -> dict:
    """Respuesta lista para el bot: ya filtrada, ya recortada, ya en hora de Colombia."""
    hoy = datetime.now(_TZ).date()
    try:
        inicio = max(dt_date.fromisoformat(desde), hoy) if desde else hoy
    except (ValueError, TypeError):
        inicio = hoy
    try:
        fin = dt_date.fromisoformat(hasta) if hasta else inicio + timedelta(days=14)
    except (ValueError, TypeError):
        fin = inicio + timedelta(days=14)
    if fin <= inicio:
        fin = inicio + timedelta(days=1)

    encontrados = await slots_disponibles(inicio.isoformat(), fin.isoformat())

    if encontrados:
        dias = [
            {
                "fecha": fecha,
                "dia_semana": dia_semana(fecha),
                "horas": horas[: config.CAL_MAX_HORAS_MOSTRAR],
            }
            for fecha, horas in list(encontrados.items())[: config.CAL_MAX_DIAS_MOSTRAR]
        ]
        return {
            "hay_disponibilidad": True,
            "dias": dias,
            "proxima_fecha": dias[0]["fecha"],
            "mensaje": (
                "Disponibilidad real. Ofrece SOLO estas fechas y estas horas. "
                "PROHIBIDO mencionar cualquier otro día u hora."
            ),
        }

    # Nada en el rango pedido: buscar el primer día con cupo dentro del horizonte.
    horizonte = inicio + timedelta(days=config.CAL_HORIZONTE_DIAS)
    extendido = await slots_disponibles(fin.isoformat(), horizonte.isoformat())
    if not extendido:
        return {
            "hay_disponibilidad": False,
            "dias": [],
            "proxima_fecha": None,
            "mensaje": (
                f"SIN CUPOS en los próximos {config.CAL_HORIZONTE_DIAS} días. "
                "No ofrezcas ninguna fecha. Responde [ESCALAR_HUMANO]."
            ),
        }

    fecha, horas = next(iter(extendido.items()))
    return {
        "hay_disponibilidad": False,
        "dias": [],
        "proxima_fecha": fecha,
        "dia_semana": dia_semana(fecha),
        "horas": horas[: config.CAL_MAX_HORAS_MOSTRAR],
        "mensaje": (
            f"SIN CUPOS antes del {fecha}. Dile al paciente que no hay cupo antes y "
            f"ofrécele ÚNICAMENTE el {dia_semana(fecha)} {fecha} con esas horas. "
            "PROHIBIDO ofrecer cualquier otra fecha, aunque el paciente insista."
        ),
    }
