-- Migration 001: booking deduplication ledger foundation.
--
-- Creates the ledger table that becomes the single source of truth for
-- per-patient booking deduplication (see SDD change
-- fix-booking-duplicate-and-race, slice S1). Deliberately does NOT create
-- the `ux_reserva_activa_paciente` unique index yet -- that enforcement
-- switch is migration 002, gated behind a production backfill (slice S3).
-- Deploying this migration alone is behaviorally identical to the current
-- app: the table exists but nothing reads or writes it until S2.
--
-- `telefono_norm` / `paciente_norm` are GENERATED ALWAYS AS (...) STORED so
-- every writer (this app, and any future n8n raw-SQL node) computes the
-- dedup key identically at write time -- there is no second, drifting
-- normalization implementation to keep in sync. The expression MUST be
-- IMMUTABLE: unaccent() is STABLE (dictionary-backed) and is NOT allowed in
-- a generated column, so diacritic stripping uses translate() instead.

CREATE TABLE reservas_primera_angelical (
  id              bigserial PRIMARY KEY,
  telefono        text NOT NULL,
  paciente        text NOT NULL,
  telefono_norm   text GENERATED ALWAYS AS (regexp_replace(telefono, '[^0-9]', '', 'g')) STORED,
  paciente_norm   text GENERATED ALWAYS AS (
      btrim(regexp_replace(
        lower(translate(paciente,
          'áàäâãéèëêíìïîóòöôõúùüûñçÁÀÄÂÃÉÈËÊÍÌÏÎÓÒÖÔÕÚÙÜÛÑÇ',
          'aaaaaeeeeiiiiooooouuuuncAAAAAEEEEIIIIOOOOOUUUUNC')),
        '[^a-z0-9]+', ' ', 'g'),
      ' ')
  ) STORED,
  cal_uid         text,
  fecha           date NOT NULL,
  hora            time NOT NULL,
  estado          text NOT NULL DEFAULT 'activa',
  created_at      timestamptz NOT NULL DEFAULT now(),
  confirmed_at    timestamptz,
  motivo_cierre   text
);

-- Guards against inserting two ledger rows for the same Cal.com booking
-- (e.g. a retried backfill). NULL cal_uid rows (pending inserts before the
-- Cal.com call completes) are excluded from this constraint.
CREATE UNIQUE INDEX ux_reserva_cal_uid
  ON reservas_primera_angelical (cal_uid) WHERE cal_uid IS NOT NULL;

-- Session lock table (backing app/db.py lock_sesion/unlock_sesion, added in
-- slice S4). Created here because it shares this migration's scope and has
-- no dependency on the ledger enforcement cutover.
CREATE TABLE sesiones_bot_angelical (
  telefono   text PRIMARY KEY,
  ejecucion  text NOT NULL,
  expira_at  timestamptz NOT NULL
);
