"""Python mirror of the Postgres normalization used by the booking ledger.

IMPORTANT: this module is a MIRROR for message text (e.g. composing the
`NO SE AGENDÓ: ...` rejection copy), never the deduplication authority. The
authority is the `telefono_norm` / `paciente_norm` GENERATED ALWAYS AS (...)
STORED columns in `migrations/001_reservas_ledger.sql` -- the partial unique
index over those columns is what actually prevents a duplicate booking.

`tests/test_normalize_parity.py` asserts this mirror agrees with the SQL
generated column over a fixture corpus. If this file and the SQL expression
ever diverge, that divergence is invisible everywhere except that test --
which is exactly the silent-failure mode this design exists to prevent.
Any change here MUST be mirrored in migrations/001_reservas_ledger.sql (and
vice versa).
"""

import re

_ACENTOS_ORIGEN = "áàäâãéèëêíìïîóòöôõúùüûñçÁÀÄÂÃÉÈËÊÍÌÏÎÓÒÖÔÕÚÙÜÛÑÇ"
_ACENTOS_DESTINO = "aaaaaeeeeiiiiooooouuuuncAAAAAEEEEIIIIOOOOOUUUUNC"
_TRANSLATE_TABLE = str.maketrans(_ACENTOS_ORIGEN, _ACENTOS_DESTINO)

_NO_ALFANUMERICO = re.compile(r"[^a-z0-9]+")
_NO_DIGITO = re.compile(r"[^0-9]")


def normalizar_identidad(paciente: str) -> str:
    """Mirrors the `paciente_norm` generated column.

    Case-folds, strips Spanish diacritics via translate() (never unaccent(),
    which is STABLE and illegal in a Postgres generated column), collapses
    punctuation/whitespace runs to a single space, and trims.
    """
    minusculas = paciente.translate(_TRANSLATE_TABLE).lower()
    colapsado = _NO_ALFANUMERICO.sub(" ", minusculas)
    return colapsado.strip()


def normalizar_telefono(telefono: str) -> str:
    """Mirrors the `telefono_norm` generated column: digits only."""
    return _NO_DIGITO.sub("", telefono)
