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

## AES File Service (project-folder mirror)
- **Service**: Node/Express `aes-file-service-v0` on the AES Windows server
  (source: `F:\AESFileService`, `src/server.js`; run via NSSM). Resolves a
  5-digit job number to its project folder from a periodic scan of
  `storage.rootDirectory` (projects live one level down: `<root>\<group>\NNNNN - Name`).
- **Files (logistics side)**: `app.py` — `upload_to_aes`, `upload_files_to_aes`,
  `upload_delivery_photos_to_aes`, `aes_filename`.
- **Env**: `AES_API_URL` (e.g. `http://<host>:3001`) + `AES_API_KEY` — env only,
  app refuses to start without them. `AES_API_KEY` must equal the service's
  **`API_KEY` env var** (`server.js` checks `process.env.API_KEY`; the
  `authentication.apiKey` in its `config.json` is *not* what `/api/upload` checks).
- **Call** (corrected 2026-09-23 — the previous `POST /api/files/upload` with
  `logisticsId`/`directoryPath` does not exist on the service and 404'd):
  `POST {AES_API_URL}/api/upload`, header `X-API-Key`, multipart:
  `file`, `projectNumber` (job number), `fileType`, `filename`
  (`<Prefix>_Job<n>_<YYYYMMDD-HHMMSS>_<8hex>_<label>.<ext>`; unique because the
  service overwrites same-name files).
  → `200 {success:true, fileName, destinationPath, projectName, ...}` ·
  `400 {success:false, error}` (e.g. `Project not found: <n>`, `Unsupported file type`) ·
  `401` bad key.
- **fileType → destination** (service `config/file-types.json`):

  | fileType | Destination under project folder | Sent when |
  |---|---|---|
  | `packing_slip` | `PROJECT MANAGEMENT\Accounting Docs\Purchase Orders and Packing Slips\Packing Slips` | Incoming wizard **finalize** (each slip page) |
  | `intake_photo` | `CORRESPONDENCE\Intake Photos` | Incoming wizard **finalize** (each pallet photo) |
  | `delivery_photo` | `CORRESPONDENCE\Delivery Photos` | Scheduled delivery **complete** (signature + photos) |

  `intake_photo` + `delivery_photo` were added to the service's `file-types.json`
  on 2026-09-23 (requires a service restart to load).
- **Failure**: non-fatal. Result is returned to the caller as
  `file_service: {success, uploaded, failed:[{file,error}]}` on `/complete` and `/finalize`.
- **Ad-hoc sync** (`/api/upload` on *this* app) still has no handler (001 WS-3).

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
- [x] Purge hardcoded `AES_API_KEY` (F2) — read from env only (A1).
- [x] Rewire File Service calls to the real `/api/upload` contract; mirror incoming slips + pallet photos.
- [ ] Decide whether ad-hoc `/api/upload` mirrors to AES (001-WS-3).
- [ ] Verify auth-service admin endpoints + error surface (timeout/503) are handled by callers.
- [ ] Add a config-absence table test: each integration returns its sentinel when env unset.