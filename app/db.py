import asyncpg
from app.config import DATABASE_URL

_pool: asyncpg.Pool | None = None


async def get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=5, statement_cache_size=0)
    return _pool


async def close_pool():
    global _pool
    if _pool:
        await _pool.close()
        _pool = None


# ── Dashboard KPIs ──────────────────────────────────────────

async def dashboard_metrics(pool: asyncpg.Pool) -> dict:
    row = await pool.fetchrow("""
        SELECT
            (SELECT COUNT(*) FROM conversaciones_angelical
             WHERE ultimo_mensaje_at > NOW() - INTERVAL '24 hours')::int
                AS conversaciones_hoy,
            (SELECT COUNT(*) FROM conversaciones_angelical
             WHERE ultimo_mensaje_at > NOW() - INTERVAL '24 hours'
               AND total_mensajes <= 2)::int
                AS nuevos_hoy,
            (SELECT COUNT(*) FROM conversaciones_angelical
             WHERE ultimo_mensaje_at > NOW() - INTERVAL '24 hours'
               AND total_mensajes > 2)::int
                AS recurrentes_hoy,
            (SELECT COUNT(*) FROM citas_control_angelical
             WHERE estado = 'activa'
               AND fecha::date >= CURRENT_DATE
               AND fecha::date < CURRENT_DATE + INTERVAL '7 days')::int
                AS citas_semana,
            (SELECT COUNT(*) FROM escalados_angelical
             WHERE escalado = TRUE)::int
                AS escalados_pendientes,
            (SELECT COUNT(*) FROM conversaciones_angelical
             WHERE total_mensajes >= 2
               AND total_mensajes % 2 = 0
               AND ultimo_mensaje_at < NOW() - INTERVAL '1 hour')::int
                AS abandonadas
    """)
    return dict(row)


async def daily_chart(pool: asyncpg.Pool, days: int = 7) -> list[dict]:
    rows = await pool.fetch("""
        SELECT to_char(d.dia, 'Dy DD') AS dia,
               COALESCE(c.mensajes, 0)::int AS mensajes
        FROM generate_series(
            CURRENT_DATE - $1::int * INTERVAL '1 day',
            CURRENT_DATE,
            '1 day'
        ) AS d(dia)
        LEFT JOIN (
            SELECT date(ultimo_mensaje_at) AS fecha, COUNT(*) AS mensajes
            FROM conversaciones_angelical
            WHERE ultimo_mensaje_at > NOW() - ($1::int + 1) * INTERVAL '1 day'
            GROUP BY date(ultimo_mensaje_at)
        ) c ON date(d.dia) = c.fecha
        ORDER BY d.dia
    """, days)
    return [dict(r) for r in rows]


async def citas_chart(pool: asyncpg.Pool, days: int = 7) -> list[dict]:
    rows = await pool.fetch("""
        SELECT to_char(d.dia, 'Dy DD') AS dia,
               COALESCE(c.total, 0)::int AS citas
        FROM generate_series(
            CURRENT_DATE - $1::int * INTERVAL '1 day',
            CURRENT_DATE + INTERVAL '6 days',
            '1 day'
        ) AS d(dia)
        LEFT JOIN (
            SELECT fecha::date AS fecha, COUNT(*) AS total
            FROM citas_control_angelical
            WHERE estado = 'activa'
              AND fecha::date >= CURRENT_DATE - $1::int
            GROUP BY fecha::date
        ) c ON d.dia = c.fecha
        ORDER BY d.dia
    """, days)
    return [dict(r) for r in rows]


# ── Citas ──────────────────────────────────────────────────

async def get_citas(pool: asyncpg.Pool) -> list[dict]:
    rows = await pool.fetch("""
        SELECT id, nombre, telefono, email, motivo,
               fecha::date AS fecha, hora::time AS hora, estado
        FROM citas_control_angelical
        WHERE estado = 'activa'
          AND (fecha::date > CURRENT_DATE OR
              (fecha::date = CURRENT_DATE AND hora::time >= CURRENT_TIME))
        ORDER BY fecha, hora
        LIMIT 50
    """)
    return [dict(r) for r in rows]


async def cancelar_cita(pool: asyncpg.Pool, cita_id: int) -> bool:
    result = await pool.execute(
        "UPDATE citas_control_angelical SET estado='cancelada' "
        "WHERE id=$1 AND estado='activa'",
        cita_id,
    )
    return "UPDATE 1" in result


# ── Escalados ──────────────────────────────────────────────

async def get_escalados(pool: asyncpg.Pool) -> list[dict]:
    rows = await pool.fetch("""
        SELECT telefono, escalado_at
        FROM escalados_angelical
        WHERE escalado = TRUE
        ORDER BY escalado_at DESC
    """)
    return [dict(r) for r in rows]


async def liberar_escalado(pool: asyncpg.Pool, telefono: str) -> bool:
    result = await pool.execute(
        "UPDATE escalados_angelical SET escalado=FALSE WHERE telefono=$1 AND escalado=TRUE",
        telefono,
    )
    return "UPDATE 1" in result


# ── Pausados ───────────────────────────────────────────────

async def get_pausados(pool: asyncpg.Pool) -> list[dict]:
    rows = await pool.fetch("""
        SELECT telefono
        FROM bot_pausado_angelical
        WHERE pausado = TRUE
        ORDER BY telefono
    """)
    return [dict(r) for r in rows]


async def reanudar_bot(pool: asyncpg.Pool, telefono: str) -> bool:
    result = await pool.execute(
        "UPDATE bot_pausado_angelical SET pausado=FALSE WHERE telefono=$1 AND pausado=TRUE",
        telefono,
    )
    return "UPDATE 1" in result


async def pausar_bot(pool: asyncpg.Pool, telefono: str) -> bool:
    result = await pool.execute(
        "INSERT INTO bot_pausado_angelical (telefono, pausado) VALUES ($1, TRUE) "
        "ON CONFLICT (telefono) DO UPDATE SET pausado = TRUE",
        telefono,
    )
    return "INSERT" in result or "UPDATE" in result


# ── Recientes ──────────────────────────────────────────────

async def get_recientes(pool: asyncpg.Pool) -> list[dict]:
    rows = await pool.fetch("""
        SELECT telefono, ultimo_mensaje, ultimo_mensaje_at, total_mensajes
        FROM conversaciones_angelical
        WHERE ultimo_mensaje_at > NOW() - INTERVAL '48 hours'
        ORDER BY ultimo_mensaje_at DESC
        LIMIT 30
    """)
    return [dict(r) for r in rows]


async def is_pausado(pool: asyncpg.Pool, telefono: str) -> bool:
    row = await pool.fetchrow(
        "SELECT 1 FROM bot_pausado_angelical WHERE telefono=$1 AND pausado=TRUE",
        telefono,
    )
    return row is not None


# ── Agendar Control ──────────────────────────────────────

_HOLIDAYS_2026 = {
    '2026-01-01', '2026-01-12', '2026-03-23', '2026-04-02', '2026-04-03',
    '2026-05-01', '2026-05-18', '2026-06-08', '2026-06-15', '2026-06-29',
    '2026-07-20', '2026-08-07', '2026-08-17', '2026-10-12', '2026-11-02',
    '2026-11-16', '2026-12-08', '2026-12-25',
}

_VALID_WEEKDAYS = {2, 3, 5, 6}  # Tue, Wed, Fri, Sat

_VACACIONES_INICIO = '2026-07-23'
_VACACIONES_FIN = '2026-07-29'


def is_valid_appointment_date(fecha: str) -> bool:
    from datetime import date as dt_date
    try:
        d = dt_date.fromisoformat(fecha)
    except (ValueError, TypeError):
        return False
    if _VACACIONES_INICIO <= fecha <= _VACACIONES_FIN:
        return False
    if fecha in _HOLIDAYS_2026:
        return False
    if d.isoweekday() not in _VALID_WEEKDAYS:
        return False
    return True


def invalid_date_error(fecha: str) -> str:
    from datetime import date as dt_date
    try:
        d = dt_date.fromisoformat(fecha)
    except (ValueError, TypeError):
        return "Fecha inválida"
    if _VACACIONES_INICIO <= fecha <= _VACACIONES_FIN:
        return "Vacaciones del 23 al 30 de julio. No se agendan citas. Se retoma el 31 de julio."
    if fecha in _HOLIDAYS_2026:
        return f"{fecha} es festivo. No se agendan citas."
    dias = {1: 'lunes', 2: 'martes', 3: 'miércoles', 4: 'jueves', 5: 'viernes', 6: 'sábado', 7: 'domingo'}
    return f"Solo atendemos martes, miércoles, viernes y sábado (seleccionó {dias[d.isoweekday()]})"


async def get_control_slots(pool: asyncpg.Pool, fecha: str) -> list[str]:
    from datetime import date as dt_date
    if not is_valid_appointment_date(fecha):
        return []
    fecha_date = dt_date.fromisoformat(fecha)
    rows = await pool.fetch(
        """
        WITH slots AS (
            SELECT generate_series(
                '2026-01-01 09:00'::timestamp,
                '2026-01-01 11:00'::timestamp,
                '15 minutes'::interval
            )::time AS hora
        ),
        ocupados AS (
            SELECT hora FROM citas_control_angelical
            WHERE fecha::date = $1::date AND estado = 'activa'
        )
        SELECT s.hora::text AS hora_full, SUBSTRING(s.hora::text, 1, 5) AS hora
        FROM slots s
        LEFT JOIN ocupados o ON SUBSTRING(s.hora::text, 1, 5) = SUBSTRING(o.hora::text, 1, 5)
        WHERE o.hora IS NULL
        ORDER BY s.hora
        """,
        fecha_date,
    )
    return [r["hora"] for r in rows]


async def insert_control(
    pool: asyncpg.Pool,
    nombre: str,
    telefono: str,
    email: str,
    fecha: str,
    hora: str,
    motivo: str,
) -> dict:
    from datetime import date as dt_date, time as dt_time
    fecha_date = dt_date.fromisoformat(fecha)
    hora_time = dt_time.fromisoformat(hora)
    row = await pool.fetchrow(
        """
        INSERT INTO citas_control_angelical (nombre, telefono, email, fecha, hora, motivo)
        VALUES ($1, $2, $3, $4::date, $5::time, $6)
        RETURNING id, nombre, fecha, hora
        """,
        nombre, telefono, email, fecha_date, hora_time, motivo,
    )
    return dict(row)


# ── Reservas primera consulta (ledger) ──────────────────────
#
# Deduplication authority for validar_y_agendar() (app/cal.py). The
# `estado='activa'` gate against a duplicate patient is a partial unique
# index (ux_reserva_activa_paciente, migration 002 -- enabled only after the
# S3 backfill), not a read-then-write check in this module. These helpers
# only cover the ledger row lifecycle wired in S1; the T1/T2 ordering that
# calls insert_reserva() before Cal.com and confirmar_reserva()/cerrar_reserva()
# after is added in S2.

async def insert_reserva(
    pool: asyncpg.Pool,
    telefono: str,
    paciente: str,
    fecha: str,
    hora: str,
) -> dict:
    """T1: gate insert. estado defaults to 'activa', cal_uid/confirmed_at stay
    NULL until confirmar_reserva() runs after the Cal.com call succeeds."""
    from datetime import date as dt_date, time as dt_time
    fecha_date = dt_date.fromisoformat(fecha)
    hora_time = dt_time.fromisoformat(hora)
    row = await pool.fetchrow(
        """
        INSERT INTO reservas_primera_angelical (telefono, paciente, fecha, hora)
        VALUES ($1, $2, $3::date, $4::time)
        RETURNING id, telefono_norm, paciente_norm, fecha, hora, estado, created_at
        """,
        telefono, paciente, fecha_date, hora_time,
    )
    return dict(row)


async def confirmar_reserva(pool: asyncpg.Pool, reserva_id: int, cal_uid: str) -> bool:
    """T2 success path: stamps the Cal.com booking id, leaves estado='activa'."""
    result = await pool.execute(
        "UPDATE reservas_primera_angelical SET cal_uid=$1, confirmed_at=now() "
        "WHERE id=$2 AND estado='activa'",
        cal_uid, reserva_id,
    )
    return "UPDATE 1" in result


async def cerrar_reserva(
    pool: asyncpg.Pool,
    reserva_id: int,
    estado: str,
    motivo_cierre: str | None = None,
) -> bool:
    """Closes a ledger row (e.g. estado='fallida' compensation on Cal.com
    failure, or estado='cancelada_externa' during reconcile)."""
    result = await pool.execute(
        "UPDATE reservas_primera_angelical SET estado=$1, motivo_cierre=$2 WHERE id=$3",
        estado, motivo_cierre, reserva_id,
    )
    return "UPDATE 1" in result


async def buscar_activa(pool: asyncpg.Pool, telefono_norm: str, paciente_norm: str) -> dict | None:
    """Looks up the active ledger row (if any) for a normalized (phone, name)
    pair. Used for reconcile lookups and pending-row sweeps."""
    row = await pool.fetchrow(
        """
        SELECT id, telefono, paciente, telefono_norm, paciente_norm, cal_uid,
               fecha::date AS fecha, hora::time AS hora, estado, created_at, confirmed_at
        FROM reservas_primera_angelical
        WHERE telefono_norm = $1 AND paciente_norm = $2 AND estado = 'activa'
        """,
        telefono_norm, paciente_norm,
    )
    return dict(row) if row else None
