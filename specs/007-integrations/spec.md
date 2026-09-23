# Spec 007 — External Integrations

Each integration **degrades gracefully**: no env/config → returns a sentinel
(`None`/`(False, err)`) rather than raising, so a delivery never blocks on an
unconfigured service.

## Auth-service (microservice)
- **Files**: `auth_utils.py`, `auth_routes.py`.
- **URL**: `AUTH_SERVICE_URL` (default `https://auth-service-production-bb0d.up.railway.app`).
- **Calls**: `POST /api/auth/login`; auth-service-side admin: `register_user`,
  `users`, `users/<id>` (DELETE) via `call_auth_service()`.
- **Status**: replaces the deleted embedded `auth.py` (F5). **Decorators still
  don't verify role/token** (F3) — see `004-auth`.

## AES File Service (photo mirror)
- **Files**: `app.py` (`upload_to_aes`, `upload_delivery_photos_to_aes`,
  `generate_aes_filename`).
- **Env**: `AES_API_URL` (default raw IP `http://71.172.107.128:3001`) +
  `AES_API_KEY` (**hardcoded real key at `app.py:93` — F2**).
- **Call**: `POST {AES_API_URL}/api/files/upload` multipart `file`
  (`<DIRECTORY>_<SHIPMENT>_<ts>_<hash>.<ext>`), form `logisticsId` +
  `directoryPath`, header `X-API-Key`. Response `{success, data:{fileId,fileName,...}}`.
- **When**: on scheduled-delivery **complete** (signature + photos). Non-fatal on failure.
- **Ad-hoc sync** (`/api/upload`) does not mirror at HEAD (see 001-open) — **verify intended**.

## SMTP (emailer.py)
- Env `SMTP_HOST/PORT/USERNAME/PASSWORD/FROM/USE_TLS`; `send_flag_email(to,subject,body,attachment_paths)`.
- Returns `(ok, err)`; missing config → `(False, "SMTP not configured…")`.
- Used by: flag alert (PMteam), send-copy-to-PM, schedule reminders, daily report
  (broken F5), completion emails (PM+receiver).

## Twilio SMS (sms.py)
- Env `TWILIO_ACCOUNT_SID/AUTH_TOKEN/FROM_NUMBER`; `send_sms(to, body)` → `(ok, err)`.
- "Driver on the way" text on `/api/schedule/<id>/start`. Trial accounts: verified numbers only.

## Google Maps Distance Matrix (maps.py)
- Env `GOOGLE_MAPS_API_KEY`; `get_eta(lat,lng,address)` → dict or `None`.
- Requires billing-enabled project. ETA text shown in start result/email.

## ICS calendar (scheduling.py)
- URL stored in `schedule_store.json settings.ics_url`; `fetch_upcoming_events()`
  parses `VEVENT` (dtstart relative-day handling) — read-only, 14-day window.

## Contracts
Relevant request/response for each in `001-server/contracts/api.md`.
Any change here updates this spec in the same commit.

## Tasks
- [ ] Purge hardcoded `AES_API_KEY` (F2) — read from env only; file `.env.example` key name.
- [ ] Decide whether ad-hoc `/api/upload` mirrors to AES (001-WS-3).
- [ ] Verify auth-service admin endpoints + error surface (timeout/503) are handled by callers.
- [ ] Add a config-absence table test: each integration returns its sentinel when env unset.