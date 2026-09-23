# Spec 005 — Inventory: Plan & Tasks

## Plan
1. **Decision: extend server to the wizard contract** (matches shipped UX; single
   source of truth in `001-server/contracts/api.md`).
2. Add session-backed Incoming wizard on the server (in-memory session store or
   staged files keyed by session id), reusing OCR + `inventory.py`.
3. Expose `GET /api/inventory/pms` (filter auth-service users pm/admin) and
   `GET /api/schedule/warehouse/ready_to_pack`.
4. Fix daily report recipient source (auth-service), not by restoring `auth.py`.

## Tasks
- [ ] Server: `POST /api/incoming/scan_page` (multipart `photo`, optional `session_id`) → `{session_id,job_number_guess,po_number_guess}`.
- [ ] Server: `POST /api/incoming/confirm_job` (`{session_id,job_number,po_number,staff,pm_email?}`) → `needs_pm` iteration; email PM.
- [ ] Server: `POST /api/incoming/pallet_photo` (`{session_id,photo}`).
- [ ] Server: `POST /api/incoming/finalize` (`{session_id,pallet_count,locations,comment}`) → ledger + QR → `{qr_pdf_url}`.
- [ ] Server: `GET /api/inventory/pms`; `GET /api/schedule/warehouse/ready_to_pack`.
- [ ] Job→PM directory memo (`get/set_pm_for_job`) wired into confirm flow.
- [ ] Daily report fix (F5).
- [ ] Tests: location-split invariant, mark-shipped on pack, PM directory.