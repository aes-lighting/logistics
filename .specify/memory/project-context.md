# Project Context — AES Logistics (HEAD ground truth)

This file records what the repo **actually is** at `HEAD` (`5b47c99`), surveyed
from the working tree and the 49-commit history. Treat declarations here as the
authority; the README is stale on several axes.

## Identity

- Repo: `aes-lighting/logistics` (private org). Main branch. 49 commits.
- Built around 2026-08/09; last commit 2026-09-11 ("Stop tracking .env file for security").
- Serves AES Lighting Group (Whippany, NJ) delivery-logistics + inventory.

## History spine (selected commits)

| SHA | Event |
|---|---|
| `f8599d9` | Initial commit |
| `8c92283` | **Removed embedded `auth.py`**; proxied auth to external `auth-service` microservice (Railway). This is when README/.env/docker auth text went stale. |
| `31edcc0` | "Restore full app.py with all logistics endpoints" (kept auth-service integration) |
| `94881a7` | Corrected AES upload params/endpoint |
| `a0286f5` | "Remove sensitive API configurations from .env" |
| `5b47c99` | "Stop tracking .env file for security" — **but `.env` is still in `git ls-files` at HEAD** |

## ⚠️ Live findings (must-read)

### F1 — `.env` with real secrets is git-tracked at HEAD
`git ls-files` lists `.env` (and `.env.example`, `server/.env.example`).
The tip commit claiming to untrack it did **not** actually remove it from the
index (`git rm --cached` never landed). `.gitignore` has a **broken rule** —
`**\.env ` and `.env ` carry a **trailing space**, so `git check-ignore .env`
matches nothing. Content includes real `AES_API_KEY`, `FLASK_SECRET_KEY`,
`AES_API_URL=http://71.172.107.128:3001`, and legacy `FILE_SERVICE_URL` /
`AUTH_SERVICE_URL` / `ADMIN_PASSWORD`.

### F2 — Hardcoded API key in source
`server/app.py:92-93` defaults `AES_API_URL` to the raw-IP service and
`AES_API_KEY` to a **real-looking 64-char key** when env isn't set. Even after
`.env` is untracked, the key remains in `app.py`.

### F3 — Auth trust gap
Role decorators check only that *some* `Authorization: Bearer <email>` string is
present; they do **not** call auth-service to verify the token/role (`TODO`s in
`auth_decorators.py`). The PM portal sends `Bearer <email>` from localStorage —
so **any email string in the header is accepted as that user**, with no
integrity check → privilege escalation + impersonation at the API layer.
Mitigations may exist at the network layer (HTTPS + proxy), but the app
treats an unverified string as an authenticated principal.

### F4 — Frontend/backend contract mismatch (Incoming Inventory + delivery APIs)
The frontends call routes the server does not implement, and vice-versa:

- **Frontend calls** (`driver_app/app.js`): `/api/incoming/scan_page`,
  `/api/incoming/confirm_job`, `/api/incoming/pallet_photo`,
  `/api/incoming/finalize`, `/api/inventory/pms`,
  `/api/schedule/warehouse/ready_to_pack`, `/send_to_pm`,
  `file/<ticket_filename>`.
- **Server implements** (`server/app.py`): `/api/incoming/scan`,
  `/api/incoming/confirm`, `/api/incoming/flag`, `/api/schedule/pms`,
  `/send_copy_to_pm`, `file/<int>`; no `warehouse/ready_to_pack`;
  no `inventory/pms` (only `inventory/locations`, `/api/inventory`,
  `/api/inventory/<id>/remove`, `/api/inventory/export`).
→ Full table in `specs/001-server/contracts/api.md`. The app is **not
functional end-to-end** for Incoming Inventory / Ready-to-Pack / Send-to-PM at
HEAD until one side or the other is aligned.

### F5 — Broken cron script
`server/send_daily_inventory_report.py` does `import auth` and calls
`auth.list_users()` — `auth.py` was deleted in `8c92283`. Raises
`ModuleNotFoundError` on run. Recipient enumeration must switch to the
auth-service admin/users call used elsewhere.

### F6 — Legacy references
- `docker-compose.yml` mounts `./data/auth_store.json` (unused at HEAD).
- Root `.env.example` still lists `FILE_SERVICE_URL`/`AUTH_SERVICE_URL`/
  `ADMIN_PASSWORD` (superseded by `server/.env.example`).
- `send_daily_inventory_report.py` calls `auth.list_users()` (see F5).

## Working truths (verified at HEAD)

- Ad-hoc sync: driver app POSTs **`/api/upload`** (multipart metadata+photos) —
  server's file-service upload is keyed off scheduled-complete path, not this.
  Confirm against `app.py` before assuming ad-hoc sync is wired.
- Scheduled complete: server requires ≥2 photos + signature name/Blob; emails PM
  + receiver; mirrors to AES File Service (non-fatal on failure).
- Inventory link: packing a delivery auto-`mark_removed_by_job`; manual Mark
  Shipped for partials.
- OCR patterns live in `server/server_config.json` (job + PO), shared across flows.
- Storage roots are relative (`./incoming`, `./organized`) per `server_config.json`.