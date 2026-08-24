-- Migration 002: enable duplicate-booking enforcement.
--
-- *** DO NOT APPLY THIS TO ANY PRODUCTION OR STAGING DATABASE FROM SLICE S2 ***
--
-- Exists in S2 only so tests/test_concurrency.py and tests/test_cal_ordering.py
-- can exercise the real constraint validar_y_agendar()'s UniqueViolationError
-- handling depends on. Test schema applies 001 + 002 together; production
-- applies 001 only until S3's backfill + violator report gate clears:
--   1. Deploy 001 (S1) -- ledger table exists, unused.
--   2. Backfill reservas_primera_angelical from Cal.com (S3).
--   3. Violator report; operator resolves any duplicate groups.
--   4. ONLY THEN apply this migration (S3), gated on zero duplicate groups.
-- Applying it before backfill would enforce uniqueness against an EMPTY
-- ledger and let every real duplicate in Cal.com sail through undetected.
--
-- Plain CREATE UNIQUE INDEX (not CONCURRENTLY, which cannot run inside a
-- transaction and leaves an INVALID index on failure): table is tens of rows.

CREATE UNIQUE INDEX ux_reserva_activa_paciente
  ON reservas_primera_angelical (telefono_norm, paciente_norm)
  WHERE estado = 'activa';
