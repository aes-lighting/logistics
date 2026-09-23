# Spec 005 — Inventory (Incoming + Outgoing, locations, Excel)

## Purpose
Receive-ledger + location tracking for packing slips (Incoming) and the
packing/checkoff/sign flow (Outgoing / Ready to Pack), with a job→PM directory
auto-email and an Excel export.

## Incoming Inventory — two competing APIs (the F4 crux)
- **Server (single-shot)**: `POST /api/incoming/scan` (one `slip`) →
  `confirm` (job/PO) → moved to `Incoming_Packing_Slips/Job_<n>/` +
  `inventory.log_packing_slip`; `flag` emails PMteam.
- **Frontend wizard (as shipped)**: `scan_page` (multi-page session) →
  `confirm_job` → `pallet_photo` (one per pallet) → `finalize` (locations +
  comment) → QR PDF. Needs PM picker on first-seen job (`needs_pm`), 13 fixed
  locations, split-location counts that must sum to pallet count.

**Decision (must be made):** the shipped UX is the wizard; **extend the server**
to implement the wizard contract (add `scan_page`, `confirm_job`, `pallet_photo`,
`finalize`, `GET /api/inventory/pms`, and expose `warehouse/ready_to_pack`).
This is the sanctioned direction (also in `001-server/WS-1`).

## Outgoing / Ready to Pack
- `scheduling.deliveries_ready_to_pack()` returns `ticket_uploaded` deliveries;
  **no HTTP route exists at HEAD** (frontend calls `/api/schedule/warehouse/ready_to_pack`).
- Packing via `POST /api/schedule/<id>/pack` requires all `line_item_checks` true
  (or `checkoff_confirmed` when no line items), `packed_by`, `signature`.
- Packing auto-`mark_removed_by_job` → inventory entries for that job become
  `removed` (`packed_for_outgoing_delivery`) → drop out of active count/export.
- Manual **Mark Shipped** (`POST /api/inventory/<id>/remove`) for partials/corrections.

## Locations
13 fixed: Warehouse, Back Tent, Front Tent, Trailer 6, Trailer 4, Redbox,
Front Red, CS 1036, CS 1071, CS 1058, CS 1015, Office, Truck.
An entry may split across several with counts; invariant: sum = pallet_count.

## QR + Excel
- `qr_ticket.py` → one-page PDF (QR → `<base>/inventory/<entry_id>` + plain-text
  job/PO/pallets/locations). No printer wired; browser print dialog.
- `inventory_report.py` → `AES_Inventory_<date>.xlsx` (Current Inventory +
  Summary by Location), pm/admin only.

## Data model
See `001-server/data-model.md` (`inventory_store.json` shape). Also `import auth`
break in the daily report → `001-server/WS-2`.

## Tasks
- [ ] Decide & document: extend server to wizard contract (recommended).
- [ ] Implement the four ❌ wizard endpoints + `inventory/pms` + `ready_to_pack`.
- [ ] Wire wizard → `inventory.py`, QR, mark-shipped-on-pack.
- [ ] Fix `send_daily_inventory_report.py` (F5) — use auth-service admin/users.
- [ ] Tests for split-location invariant + mark-shipped-by-job linkage.