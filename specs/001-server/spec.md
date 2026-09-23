# Spec 001 — Server API (Flask)

## Purpose

The single Flask backend: static serving, JSON API, OCR filing, file-service
mirror, and scheduling/inventory endpoints. All persistent state is JSON files
under `server/`.

## Scope

- Routes in `server/app.py`, `auth_routes.py`.
- OCR + filing (`server_config.json` regexes).
- Static serving of `driver_app/` and `pm_portal/`.
- AES File Service mirror (`app.py`).

## Design

- `app = Flask(__name__, static_folder=None)`; manual static routes for `/`
  and `/pm` and catch-alls.
- `FLASK_SECRET_KEY` from env; random per-run if unset (warns). **Login uses no
  real server session** — see `specs/004-auth`.
- Config from `server_config.json` (`load_config()` with defaults). Keys:
  `job_number_pattern`, `po_number_pattern`, `incoming_dir`, `dest_dir`,
  `review_folder`, `incomplete_flag_filename`, `incoming_staging_dir`,
  `incoming_slip_subfolder`, `flagged_slips_folder`, `flag_alert_email_to`,
  `warehouse_alert_email`.
- OCR: `pytesseract` → `ocr_text()` → regex with **named groups** `(?P<job>…)`,
  `(?P<po>…)`.
- File-service filenames: `DIRECTORY_SHIPMENT_TIMESTAMP_HASH.ext`; uploads
  `SHIP-<delivery_id>` with `logisticsId` + `directoryPath` to
  `{AES_API_URL}/api/files/upload`, key `X-API-Key`.

## Open questions / decisions needed

1. **Ad-hoc sync `/api/upload`**: frontend POSTs it but app.py's file-mirror
   path is scheduled-complete only. Is ad-hoc mirror intended? Confirm route
   existence before declaring sync wired. → `contracts/api.md`.
2. **Contract drift F4**: server's Incoming-Inventory API (single-shot) does not
   match the frontend wizard. Decision owned by `specs/005-inventory`.
3. Static route order: `<path:filename>` catch-all may shadow `/pm/...`? Verify.

## Contracts

- Live route table + request/response shapes: `contracts/api.md`.
- Data model of JSON stores: `data-model.md`.