# Spec 001 — Server API: Plan

## Goal
Make `server/app.py` + modules the verified, single source of truth with no
contract vs. the running frontends, and clean up the known cracks (F4, F5, F6).

## Workstreams

### WS-1 Align Incoming-Inventory contract (blocks Incoming Inventory)
- **Decision first** (`specs/005-inventory`): extend server with the wizard
  endpoints the frontend already calls, OR rework frontend to single-shot API.
- Recommended: extend server (frontend is the shipped UX; least churn).
- Add: `POST /api/incoming/scan_page`, `confirm_job`, `pallet_photo`,
  `finalize`, `GET /api/inventory/pms`, `GET /api/schedule/warehouse/ready_to_pack`.
- Mirror to existing `inventory.py` ledger + `mark_removed_by_job` link.

### WS-2 Repair daily report (F5)
- Replace `import auth` / `auth.list_users()` with the auth-service
  admin/users call (same pattern as `api_schedule_drivers`). Filter pm/admin.
- Keep `PUBLIC_BASE_URL` link behavior. Target recipients unchanged.

### WS-3 Ad-hoc sync route (confirm or document)
- Decide whether `/api/upload` should mirror to AES File Service or only file
  locally + OCR. Add/align route; update `contracts/api.md`.

### WS-4 File-serving path consistency
- Align `file/<ticket_filename>` (frontend) vs `file/<int>` (server): pick one,
  keep `/api/schedule/<id>/file/ticket` for ticket, index for photos, or accept
  literal filenames. Update frontend + server together.

### WS-5 Auth enforcement (with 004-auth)
- Make `@pm_or_admin_required` / `@admin_required` actually verify role via
  auth-service (see `specs/004-auth/plan.md`).

### WS-6 Legacy refs (F6)
- Drop `auth_store.json` from docker-compose; prune root `.env.example`.

## Sequencing
1. WS-4 (lowest risk, unblocks frontends) → 2. WS-1 → 3. WS-3 → 4. WS-2 → 5. WS-5 → 6. WS-6.

## Definition of done
- `python3 server/test-app.py` passes; every route in `contracts/api.md` matches
  a live handler; frontend calls resolve; no `import auth` remains; report runs.