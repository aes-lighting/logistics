# AES Logistics — Product Deep Dive

**One-line:** a delivery-photo + receiving-ledger PWA for a small fleet (1–5
drivers) and a desk PM portal, backed by one Flask server, with end-of-shift
photo sync and a running warehouse-location inventory.

## Actors & roles

| Role | Sees (tiles) | Capabilities |
|---|---|---|
| **Driver** | Driver + Warehouse | Ad-hoc New Delivery; **My Deliveries** (assigned, packed); Warehouse pack/checkoff/sign; Incoming Inventory |
| **Warehouse** (same account type as Driver) | Driver + Warehouse | Packs & signs tickets (LOADED); Incoming Inventory (packing slips); QR labels |
| **PM** | Driver + Warehouse + Project Management | `/pm`: calendar sync, schedule, upload/generate/revise tickets, send-to-PM, inventory, mark-shipped; Register users; PM/admin export |
| **Admin** | all three | Everything PM does; user register/delete |

Role is attached to an **email**. A Driver-type account is the same person
doing two jobs (toggle via ⟲ on Home without logging out). The app menu always
shows exactly three tiles; PM/admin see all three, driver-type sees two.

## Core flows (end-to-end)

1. **Ad-hoc New Delivery** (offline-first): ticket photo + pallet photo → Complete
   → queued in IndexedDB → **Sync Now** at end of shift → server OCRs the job
   number and files into `organized/Job_<n>/` (or `needs_review_…`).
2. **Scheduled Delivery** (calendar-linked): PM pastes ICS → picks an event →
   fills job/receiver/PM/driver/date (+optional customer fields) → creates the
   record → uploads or **generates** a ticket (matches the paper Delivery
   Receipt) → Warehouse packs/checks-off/signs (LOADED) → becomes visible to the
   assigned driver → driver starts ("I'm Heading There Now" → SMS receiver +
   ETA via GPS→Google Maps) → on arrival checks off items (DELIVERED), takes
   2+ photos, receiver signs → submit emails PM + receiver with attachments
   (and uploads to AES File Service).
3. **Incoming Inventory** (packing slips, online-throughout): photo each page →
   confirm/edit job+PO (OCR-prefilled) → PM auto-emailed → pallet count + one
   photo per pallet → split across ≤13 locations → comment → Finalize →
   QR-coded printable PDF + live log + Excel export.
4. **Outgoing Inventory / Ready to Pack**: tickets awaiting Warehouse packing.
   Per delivery: **Revise Ticket**, **Send to PM**, or **Pack / Check
   Inventory**. Revising is always allowed; the system resets a packed order to
   re-pack if the driver hasn't started, and emails PM + warehouse alert each time.

## Lifecycle / state machine (scheduled delivery)

```
scheduled → ticket_uploaded → packed → en_route → completed
    │            │                               (revise: packed → ticket_uploaded
    │            │                                if not yet en_route; else keeps status)
    └            └─ reminder emailed if no ticket day-before
```

## Non-goals / known simplifications

- **No per-user passwords** (shared password by design in the old model; now
  delegated to auth-service — see `specs/004-auth` for the security gap).
- **No per-item SKU** between Incoming and Outgoing inventory — job-number-level
  link only; manual **Mark Shipped** for partials.
- **No offline retry queue** for Incoming Inventory (online throughflow) —
  unlike the ad-hoc delivery flow.
- **RECEIVED column** on the paper form is not wired; receiver's overall
  signature stands in for it.
- **No printer** wired; "Print QR" opens a PDF for the device print dialog.
- Stale README sections still claim features that migrated (auth) — do not trust them.