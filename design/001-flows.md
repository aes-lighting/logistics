# Design — Screen Map & Flows

## Driver app (PWA)

Screens (`index.html`): login → role-menu → home → (capture / complete /
scheduled-ticket / scheduled-done / start-delivery / incoming-capture /
incoming-confirm / incoming-pallets / incoming-locations / incoming-flag /
incoming-done / pack-ticket / pack-done / revise-ticket / send-to-pm).

**Flow A — Ad-hoc delivery:**
login → Driver tile → + New Delivery → [ticket photo] [pallet photo] →
Complete Delivery → "DELIVERY LOGGED" (IndexedDB queue) → Sync Now (end of shift).

**Flow B — Scheduled delivery:**
login → Driver tile → My Deliveries (packed only) → Start Delivery →
"I'm Heading There Now" (geolocate → SMS+ETA) → Continue to Ticket → per-item
checkoff (DELIVERED) → 2+ photos → receiver signs → Complete & Send.

**Flow C — Warehouse pack/checkoff:**
login → Warehouse tile → Outgoing Inventory — Ready to Pack → [Revise Ticket |
Send to PM | Pack / Check Inventory] → checkoff (LOADED) + name + signature →
"PACKED & VERIFIED".

**Flow D — Incoming Inventory wizard:**
Warehouse tile → + Incoming Inventory → photo each page (scan_page) → Done
Scanning → confirm/edit job+PO (PM picker on first-seen job) → pallet count →
one photo per pallet → split location (sum = pallet count) → comment → Finish
& Generate QR Code → "LOGGED" + Print QR.

## PM Portal (`/pm`)

Tabs: **Deliveries** (calendar sync, upcoming events → Set Up Delivery,
Schedule a Delivery form, Scheduled Deliveries table with Upload/Generate/View/
Revise/Send-to-PM/Delete) · **Inventory** (Current Inventory + Mark Shipped +
Export to Excel) · **Admin Tools** (Register a User, Registered Users +
Delete). Modals: upload, generate/revise (shared), send-to-PM, view.

**Flow E — PM schedules + tickets:**
Dashboard → paste ICS → Save → upcoming event → Set Up Delivery → fill form →
Schedule Delivery → row appears → Upload Ticket or Generate Ticket (line items)
→ (Warehouse packs) → monitor status in table → View for full record.

## UX notes
- Dark theme `#14171C`; big touch targets; stamps for completion moments.
- Role tiles always exactly three (driver sees two; pm/admin three).
- Photos store in IndexedDB; SW caches shell (never `/api/`).
- Every completion gives an explicit "nothing lost" reassurance on failure.