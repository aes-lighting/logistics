# Spec 006 — Scheduled Delivery (ticket lifecycle)

## Purpose
Calendar-linked scheduled deliveries: PM sets up from an ICS event, ticket is
uploaded or generated, Warehouse packs (LOADED), driver delivers (DELIVERED /
RECEIVED), result emailed to PM + receiver, mirrored to AES File Service.

## State machine
```
scheduled → ticket_uploaded → packed → en_route → completed
```
- `scheduled`: record created; may upload/generate ticket.
- `ticket_uploaded`: ticket present; Warehouse can pack (visible in Ready to Pack).
- `packed`: warehouse signed LOADED; driver can see (My Deliveries).
- `en_route`: driver started (SMS+ETA fired).
- `completed`: driver finished (checkoff + ≥2 photos + receiver signature + geotag).

**Revise-on-any-stage** (`revise_ticket` / `api_schedule_revise`): always allowed.
- packed (driver hasn't started) → reset to `ticket_uploaded` (re-pack), clears
  `packed_*`/`line_item_checks`, returns `reset_to_pack:true`.
- en_route/completed → status left alone (record-only correction).
- Every revision + every generate resets ticket, bumps `revision_count`, emails
  PM + warehouse alert (attach updated ticket).

## Key behavior (from `scheduling.py`)
- `deliveries_assigned_to(name)` — driver sees packed/en_route only, matched
  case-insensitive on `assigned_driver`.
- `deliveries_ready_for_driver(date)` — today's packed/en_route.
- Reminder: `send_reminders.py` emails PM for next-day deliveries lacking a ticket.
- Complete: server requires ≥2 photos, `signed_by`, signature file; emails PM +
  receiver with ticket/signature/photos; uploads to AES (non-fatal on failure).

## Contracts
- `/api/schedule*` routes in `001-server/contracts/api.md`.
- Data model (delivery record + status + checkoff arrays): `001-server/data-model.md`.

## Tasks / open items
- [ ] Align `file/<ticket_filename>` vs `file/<n>` (WS-4).
- [ ] Align `/send_to_pm` (frontend) vs `/send_copy_to_pm` (server).
- [ ] Confirm `already_scheduled` feeding in calendar upcoming (003).
- [ ] Driver-name identity key (003) — `assigned_driver` matching stability.
- [ ] Verify START SMS-only-once + ETA JSON stored shape.