import asyncpg
from app.config import DATABASE_URL

_pool: asyncpg.Pool | None = None


async def get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=5)
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

async def get_control_slots(pool: asyncpg.Pool, fecha: str) -> list[str]:
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
        LEFT JOIN ocupados o ON SUBSTRING(s.hora::text, 1, 5) = o.hora::text
        WHERE o.hora IS NULL
        ORDER BY s.hora
        """,
        fecha,
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
    row = await pool.fetchrow(
        """
        INSERT INTO citas_control_angelical (nombre, telefono, email, fecha, hora, motivo)
        VALUES ($1, $2, $3, $4::date, $5::time, $6)
        RETURNING id, nombre, fecha, hora
        """,
        nombre, telefono, email, fecha, hora, motivo,
    )
    return dict(row)
