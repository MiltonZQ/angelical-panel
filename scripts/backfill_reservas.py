"""Cutover backfill for the booking-deduplication ledger (SDD change
fix-booking-duplicate-and-race, slice S3).

Run BEFORE migration 002 (`ux_reserva_activa_paciente`) is applied to any
real database -- migration 001 must already be deployed (S1). Populates
`reservas_primera_angelical` from Cal.com so the unique index does not
enforce uniqueness against an empty ledger.

Usage:
    python scripts/backfill_reservas.py            # run the backfill
    python scripts/backfill_reservas.py --report    # read-only violator report

`--report` makes NO writes and never auto-resolves duplicate groups --
silently keeping the earliest booking would hide a real double booking. The
operator must cancel the extra Cal.com booking(s) manually.
"""

import argparse
import asyncio
import sys
from datetime import datetime, timezone

import httpx

from app import config
from app.cal import a_hora_local
from app.db import get_pool, insert_reserva_backfill, reservas_violadoras

_TAKE = 250


def _headers() -> dict:
    return {
        "cal-api-version": config.CAL_API_VERSION_BOOKINGS,
        "Authorization": f"Bearer {config.CAL_API_KEY}",
    }


async def _fetch_bookings(client: httpx.AsyncClient) -> list[dict]:
    """Paginated GET /v2/bookings, same shape as cal.citas_por_dia():
    eventTypeId + afterStart=now, take=250/page. Future, non-cancelled/
    non-rejected bookings only."""
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    bookings: list[dict] = []
    skip = 0
    while True:
        params = {"eventTypeId": config.CAL_EVENT_TYPE_ID, "afterStart": now_iso, "take": _TAKE, "skip": skip}
        resp = await client.get("https://api.cal.com/v2/bookings", params=params, headers=_headers())
        resp.raise_for_status()
        page = resp.json().get("data", []) or []
        bookings.extend(page)
        if len(page) < _TAKE:
            break
        skip += _TAKE
    return [b for b in bookings if b.get("status") not in ("cancelled", "rejected")]


def _extract(booking: dict) -> tuple[str, str, str, str, str] | None:
    """(uid, telefono, nombre, fecha, hora), or None if missing uid/start."""
    uid = booking.get("uid")
    start = booking.get("start")
    if not uid or not start:
        return None
    attendee = (booking.get("attendees") or [{}])[0] or {}
    telefono = (attendee.get("phoneNumber") or "").strip()
    nombre = (attendee.get("name") or "").strip()
    fecha, hora = a_hora_local(start)
    return uid, telefono, nombre, fecha, hora


async def _run_backfill() -> int:
    pool = await get_pool()
    inserted = skipped_existing = 0
    missing_phone: list[tuple[str, str]] = []  # (uid, nombre)

    async with httpx.AsyncClient(timeout=20) as client:
        bookings = await _fetch_bookings(client)
    print(f"Fetched {len(bookings)} active future bookings from Cal.com.")

    for booking in bookings:
        parsed = _extract(booking)
        if parsed is None:
            print(f"  SKIP (missing uid/start): {booking.get('uid')!r}")
            continue
        uid, telefono, nombre, fecha, hora = parsed

        if not telefono:
            # Empty phoneNumber -> empty telefono_norm, which would collide
            # with every other empty-phone row. Never insert blind: surface
            # for operator review instead.
            missing_phone.append((uid, nombre or "(no name)"))
            continue

        if await insert_reserva_backfill(pool, telefono, nombre, fecha, hora, uid):
            inserted += 1
        else:
            skipped_existing += 1

    print(f"Inserted: {inserted}. Already present (idempotent skip): {skipped_existing}.")

    if missing_phone:
        print(f"\nWARNING: {len(missing_phone)} booking(s) had no attendee.phoneNumber "
              "and were NOT inserted (would collide under an empty dedup key):")
        for uid, nombre in missing_phone:
            print(f"  cal_uid={uid}  attendee_name={nombre!r}")
        print("These need operator resolution: confirm phone in Cal.com and "
              "re-run, or insert manually with a verified phone number.")
    return 0


def _print_report(groups: list[dict]) -> None:
    if not groups:
        print("No duplicate active groups found. Safe to apply migration 002.")
        return
    print(f"VIOLATOR GROUPS FOUND: {len(groups)}")
    print("-" * 60)
    for g in groups:
        print(f"telefono_norm={g['telefono_norm']}  paciente_norm={g['paciente_norm']}")
        print(f"  count={g['n']}")
        print(f"  cal_uids={g['cal_uids']}")
        print("-" * 60)
    print("No auto-resolution performed. Cancel the extra Cal.com booking(s) "
          "for each group above, then re-run this report until it is empty "
          "before applying migrations/002_unique_activa.sql.")


async def _run_report() -> int:
    _print_report(await reservas_violadoras(await get_pool()))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", action="store_true",
                         help="Read-only: print duplicate-group violators. Makes no writes.")
    args = parser.parse_args()
    return asyncio.run(_run_report() if args.report else _run_backfill())


if __name__ == "__main__":
    sys.exit(main())
