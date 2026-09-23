# mvp-v1 — Build & Verification State

Status baseline: surveyed at `HEAD 5b47c99` (2026-09-11). This kit scaffolds the
repo **as it is**, including partial/broken pieces, so future work is anchored
to reality. Use `Restore`/`Known broken` markers — nothing here is claimed
verified unless marked `DONE (verified)`.

## Ad-hoc delivery (photo → OCR → organized/)

| Item | State at HEAD | Evidence |
|---|---|---|
| Driver capture: ticket + pallet, offline, IndexedDB queue | `DONE (code)` | `driver_app/app.js`, `index.html` |
| End-of-shift Sync Now → `/api/upload` | **OPEN / open contract** | frontend posts multipart; server's file-service path keys off scheduled-complete, see `contracts/api.md` |
| OCR job-number → `organized/Job_<n>/` | `DONE (code)` | `app.py:extract_job_number`, `server_config.json` |
| incomplete / needs_review fallbacks | `DONE (code)` | `app.py` |

## Scheduled delivery (ICS → ticket → pack → deliver)

| Item | State at HEAD | Evidence |
|---|---|---|
| Calendar settings/upcoming (read-only ICS) | `DONE (verified)` | README's own E2E claims; `scheduling.py` |
| Create delivery (required fields enforced) | `DONE` | `app.py:api_schedule_create` |
| Upload or generate ticket | `DONE` | `ticket_render.py`, `save_ticket_file`, `save_generated_ticket` |
| Warehouse pack + checkoff + sign (LOADED) | `DONE` | `api_schedule_pack`, `deliveries_ready_to_pack` |
| Driver "My Deliveries" (packed only) | `DONE` | `deliveries_assigned_to` |
| Start → SMS + ETA | `DONE` | `api_schedule_start`, `sms.py`, `maps.py` |
| Complete → checkoff + 2-photo + signature + geotag | `DONE` | `api_schedule_complete` (2-photo enforced) |
| Email PM + receiver on complete | `DONE` | `api_schedule_complete` |
| Revise ticket (stage-aware reset) + alert emails | `DONE` | `revise_ticket`, `api_schedule_revise` |
| Send-to-PM copy | `DONE` | `api_schedule_send_copy_to_pm` |
| Delete delivery | `DONE` | `api_schedule_delete` |

## Incoming Inventory (packing slips)

| Item | State at HEAD | Evidence |
|---|---|---|
| Server single-shot scan/confirm/flag | `DONE (code)` | `api_incoming_scan` / `_confirm` / `_flag` |
| Frontend wizard (multi-page, pallets, split locations, QR) | `DONE (code + test-client E2E)` — needs real-device run | A3: `api_incoming_scan_page|confirm_job|pallet_photo|finalize`; `contracts/api.md` |
| Job→PM directory + auto-email | `DONE (code)` | `confirm_job` + `finalize` email |
| QR-coded PDF label | `DONE (server)` | `qr_ticket.py` |
| Excel export (Current + Summary by Location) | `DONE` | `inventory_report.py` |
| End-of-day report | **BROKEN** | `send_daily_inventory_report.py` imports deleted `auth` → F5 |
| Daily reminder (next-day, no ticket) | `DONE` | `send_reminders.py` |

## Auth

| Item | State at HEAD | Evidence |
|---|---|---|
| Proxy login to auth-service | `DONE` | `auth_routes.py:login` |
| Role decorators present | `DONE (code)` | `auth_decorators.py` |
| **Decorators enforce role** | **OPEN — SECURITY GAP (F3)** | they only check header presence; `TODO`s |

## Infra

| Item | State at HEAD | Evidence |
|---|---|---|
| Docker image (python3.12 + tesseract, gunicorn) | `DONE (unverified on Docker daemon — README admits neither built nor run)` | `Dockerfile` |
| docker-compose with `./data` volumes | `DONE (contains legacy auth_store mount — F6)` | `docker-compose.yml` |
| Railway config | `DONE` | `railway.json` |
| `start.sh` cloudflared tunnel + launcher .bat | `DONE` | `start.sh`, `AES_Logistics_Launcher.bat` |
| **CI / test suite** | **MISSING** — only `test-app.py` import smoke test | — |

## Known-broken / must-decide

1. ~~Incoming Inventory frontend↔server contract (F4)~~ — **resolved by A3**
   (server extended to the wizard contract; see `contracts/api.md`).
2. **High-availability note**: single JSON-writer model; no locking/atomicity.
3. Secrets purge per `ops/security.md` before any public exposure.