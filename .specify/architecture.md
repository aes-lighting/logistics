# AES Logistics — Architecture

## System shape

One **Flask app** (`server/app.py`) serves everything. No queue, no DB engine —
persistence is **JSON files** on the server plus client **IndexedDB/localStorage**.

```
                       ┌──────────────────────────────┐
 driver_app  (PWA) ───▶│  server/app.py  (Flask)      │──▶ external services
 pm_portal   (/pm) ───▶│  serves statics + JSON API    │    ├ auth-service (Railway)
                       └──────────────────────────────┘    ├ AES File Service (raw IP)
                                                          ├ SMTP (emailer.py)
                                                          ├ Twilio (sms.py)
                                                          ├ Google Maps (maps.py)
                                                          └ ICS feed (scheduling.py)
```

## Server modules

| File | Responsibility |
|---|---|
| `app.py` | Flask app; all routes; OCR helpers; AES File Service client |
| `auth_routes.py` / `auth_utils.py` | Blueprint proxying login/register to **auth-service**; header parsing |
| `auth_decorators.py` | `@login_required`, `@admin_required`, `@pm_or_admin_required` — **role checks are currently stubs** (see `specs/004-auth`) |
| `scheduling.py` | Scheduled-delivery CRUD + lifecycle; `schedule_store.json` + `schedule_files/` |
| `inventory.py` | Incoming-ledger + job→PM directory; `inventory_store.json` |
| `inventory_report.py` | Excel export (Current Inventory + Summary by Location) |
| `ticket_render.py` | PNG delivery-ticket renderer (matches paper form) |
| `qr_ticket.py` | QR-coded printable PDF for check-ins |
| `emailer.py` | SMTP (singular + attachments); returns `(ok, err)` never raises |
| `sms.py` | Twilio; returns `(ok, err)` never raises |
| `maps.py` | Google Distance Matrix ETA; returns `None`, never raises |
| `send_reminders.py` | cron: email PMs for next-day deliveries missing tickets |
| `send_daily_inventory_report.py` | cron: end-of-day report — **BROKEN** (imports deleted `auth`) |

## Persistence (server, under `server/`)

| Store | Writer |
|---|---|
| `schedule_store.json` | `scheduling.py` — deliveries dict + `settings.ics_url` |
| `inventory_store.json` | `inventory.py` — entries + `job_pm_directory` |
| `schedule_files/<delivery_id>/` | tickets, signatures, photos |
| `incoming/` `organized/` | OCR filing (ad-hoc delivery) & packing-slip storage |
| `auth_store.json` | **NOT used at HEAD** — legacy from embedded-auth era (README/docker still reference it) |

Persistence model is intentionally AWS-free/DB-free: JSON snapshots.
Concurrency: no locking; single-writer assumption (small fleet). See
`specs/001-server/data-model.md`.

## Auth flow (HEAD)

Login is a **proxy**: `POST /api/auth/login` → auth-service verifies email/
password → returns `{role,name,email}`. The client stores this in
`localStorage` and sends it back on the `Authorization: Bearer <email>` header
(PM portal) or via body/`credentials` (driver app does **not** attach a token
for most calls). **The server does not cryptographically validate the returned
"identity" on subsequent requests** — it trusts a bare email string. This is the
central security gap → `specs/004-auth` + `ops/security.md`.

## External integrations (all degrade gracefully — never crash the caller)

| Integration | Module | Env keys | Purpose |
|---|---|---|---|
| auth-service | `auth_utils.py` | `AUTH_SERVICE_URL` | verify login, list/register/delete users |
| AES File Service | `app.py` | `AES_API_URL`, `AES_API_KEY` | mirror delivery photos/signature + packing slips + pallet photos into the job's project folder (`POST /api/upload`) |
| SMTP | `emailer.py` | `SMTP_*` | flag/report/ticket emails |
| Twilio SMS | `sms.py` | `TWILIO_*` | "driver on the way" texts |
| Google Maps | `maps.py` | `GOOGLE_MAPS_API_KEY` | driving ETA |
| ICS calendar | `scheduling.py` | (stored ics_url) | read-only upcoming-event feed |

## Infra & deployment

- **Docker**: `Dockerfile` (python:3.12-slim + tesseract-ocr, gunicorn 2 workers);
  `docker-compose.yml` binds `./data/*` volumes. **Compose references legacy
  `auth_store.json`** → stale.
- **Railway**: `railway.json` (dockerfile builder).
- **Quick test**: `start.sh` (venv + cloudflared trycloudflare tunnel) and
  `AES_Logistics_Launcher.bat` (WSL shim).
- **Production (non-Docker)**: gunicorn behind nginx + HTTPS (README §4).

## Known architecture-level caveats

- `send_daily_inventory_report.py` imports `auth` (deleted) → crash.
- Frontend expects a richer Incoming-Inventory API than the server provides → `specs/001-server/contracts/api.md`.
- Static file routes: `/` and `/pm` serve index; `<path>` catch-all serves driver_app.
- `app.py` debug-prints paths and enables no auth on `/api/health` (intended).