# Spec 009 — Supply/Materials + JIT: Plan & Tasks

## Plan
1. **Ledger first (B4):** `supply_store.json` (`{items: {<sku>: {name, on_hand, min_threshold}}}`)
   + `/api/supply/*` (list, adjust, set-threshold) + warehouse/PM UI. Link to
   inventory entries / jobs by job-number where meaningful.
2. **Ontology in the same commit (C4):** add `SupplyItem`, `JitNeed`,
   `suppliesDelivery`; closed vocab `supplyStatus` = {in_stock, below_threshold, reorder}.
3. **JIT candidates (C2):** derive `below_threshold && within_need_date_window`
   → candidate list; one-click = create a scheduled delivery (spec 006) with the
   material link.
4. **Geofence close (C3):** arrival event (spec 010) marks the JIT delivery's
   materials received; refresh on-hand + clear the candidate.

## Tasks
- [ ] B4: `supply_store.json` + `/api/supply/*` + UI.
- [ ] C4: ontology `SupplyItem`/`JitNeed`/`supplyStatus`; regenerate + validate.
- [ ] C2: need-date window + below-threshold detection; JIT candidate endpoint.
- [ ] C2: JIT → scheduled-delivery hand-off (reuses `create_delivery`).
- [ ] C3: geofence arrival closes JIT; on-hand refresh.
- [ ] Tests: threshold flip, window math, JIT→schedule, geofence close.