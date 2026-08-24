"""Guards the "index and write time disagree" silent-failure mode.

`app/normalize.py` is a Python mirror of `paciente_norm` / `telefono_norm`
in `migrations/001_reservas_ledger.sql`, used only for composing message
text. It is never the deduplication authority -- the SQL generated columns
and the partial unique index over them are. If the mirror and the SQL
expression ever drift apart, this is the only test that would catch it.
"""

import pytest

from app.normalize import normalizar_identidad, normalizar_telefono

FIXTURE_PACIENTES = [
    "Sra. LIGIA  Pérez",
    "ligia perez",
    "Don José Vicente",
]

FIXTURE_TELEFONOS = [
    "+57 300 123 4567",
    "573001234567",
    "+57 300 987 6543",
]


async def _paciente_norm_sql(pg_pool, paciente: str) -> str:
    row = await pg_pool.fetchrow(
        "INSERT INTO reservas_primera_angelical (telefono, paciente, fecha, hora) "
        "VALUES ('0000000000', $1, '2026-09-01', '09:00') "
        "RETURNING paciente_norm",
        paciente,
    )
    return row["paciente_norm"]


async def _telefono_norm_sql(pg_pool, telefono: str) -> str:
    row = await pg_pool.fetchrow(
        "INSERT INTO reservas_primera_angelical (telefono, paciente, fecha, hora) "
        "VALUES ($1, 'paciente de prueba', '2026-09-01', '09:00') "
        "RETURNING telefono_norm",
        telefono,
    )
    return row["telefono_norm"]


@pytest.mark.parametrize("paciente", FIXTURE_PACIENTES)
async def test_paciente_norm_matches_sql_generated_column(pg_pool, paciente):
    sql_value = await _paciente_norm_sql(pg_pool, paciente)
    assert normalizar_identidad(paciente) == sql_value


@pytest.mark.parametrize("telefono", FIXTURE_TELEFONOS)
async def test_telefono_norm_matches_sql_generated_column(pg_pool, telefono):
    sql_value = await _telefono_norm_sql(pg_pool, telefono)
    assert normalizar_telefono(telefono) == sql_value


async def test_honorific_and_bare_name_stay_distinct(pg_pool):
    """"Sra. Ligia" and "ligia" must NOT collide -- accepted residual risk,
    per spec (normalization is not fuzzy identity resolution)."""
    con_honorifico = await _paciente_norm_sql(pg_pool, "Sra. LIGIA  Pérez")
    sin_honorifico = await _paciente_norm_sql(pg_pool, "ligia perez")
    assert con_honorifico != sin_honorifico
    assert con_honorifico == normalizar_identidad("Sra. LIGIA  Pérez")
    assert sin_honorifico == normalizar_identidad("ligia perez")
