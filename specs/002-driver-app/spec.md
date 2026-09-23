# Spec 002 — Driver App (PWA)

## Purpose
Installable PWA for phones. Offline-first photo capture for deliveries, plus
Warehouse (Incoming/Outgoing inventory) and scheduled-delivery operations,
all behind a unified login with role tiles.

## Files
`driver_app/{index.html, app.js, styles.css, manifest.json, service-worker.js}`.

## Behavior (from `app.js`)
- **Login**: POST `/api/auth/login` → cache `{role,name,email}` in localStorage
  (`aes_cached_user`); role-menu → 2 tiles (Driver, Warehouse) or 3 (+Project
  Management → redirects `/pm`).
- **Ad-hoc New Delivery**: photo blobs held in memory; Complete → saved to
  IndexedDB (`aes_logistics`, DB version 2, stores `deliveries` + `incoming_queue`)
  with status `completed`; Sync Now POSTs `/api/upload` (metadata+photos) and
  deletes on success; `sync_failed` on error for retry.
- **My Deliveries**: GET `/api/schedule/driver/mine?driver_name=…`; packed/en_route only.
- **Start Delivery**: geolocation → POST `/start` (SMS+ETA), then ticket screen.
- **Scheduled complete**: checkoff per item (`unload_item_checks`) OR overall,
  ≥2 photos, signature canvas → Blob → POST `/complete`.
- **Incoming Inventory wizard** (`+ Incoming Inventory`): multi-step — `scan_page`
  per page → `confirm_job` (PM auto-email via directory; `needs_pm` picker) →
  pallet count + one photo each (`pallet_photo`) → split locations → comment →
  `finalize` → QR PDF (`window.open(qr_pdf_url)`). **Endpoints as shipped ⇒ server must implement wizard contract (F4).**
- **Outgoing / Ready to Pack**: GET `/api/schedule/warehouse/ready_to_pack`; per
  delivery: Revise (`/revise_ticket` line items), Send to PM
  (`/send_to_pm` — server: `/send_copy_to_pm` **F4**), Pack (`/pack` + signature).
- **Offline**: IndexedDB unavailable → falls back to localStorage-only; SW caches
  app shell (never `/api/`).

## Roles & tiles
- Driver account → Driver + Warehouse.
- PM/admin → + Project Management (redirect).
- Mode switch via ⟲ without logout.

## Contracts
Driver app consumes: `001-server/contracts/api.md` (auth, schedule, incoming,
inventory). Reconcile F4 rows before this spec opens that flow.

## Open questions
- Driver app sends **no `Authorization` header** on most GETs (uses
  `credentials:"same-origin"`); login/role gates rely on auth-service identity
  only at login. With F3, this means driver GETs depend on a session mechanism
  not present — **verify which calls actually pass `@login_required`** and how
  the server recognizes the driver (`driver/mine` needs `driver_name`).
- Signature canvas uses `canvas.toBlob(...)` — a non-standard helper; confirm it
  exists (may be a shim or a bug surface on real devices).