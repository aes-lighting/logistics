# Spec 009 — Supply/Materials Management + JIT Deliveries

## Purpose
Track on-hand supply/materials quantities per job + across the fleet, define
min-threshold / reorder state, and drive **just-in-time (JIT) deliveries**: when
a job's needed materials fall below threshold near the need-date, surface a JIT
delivery for scheduling.

Complements (does not replace) the Incoming/Outgoing inventory ledger (spec 005)
and scheduled-delivery lifecycle (spec 006). MVP builds B4 (ledger), C2 (JIT).

## Ontology edge
- `aesl:SupplyItem` — a tracked material with `onHandQuantity`, `minThreshold`.
- `aesl:JitNeed` — a job's materials-need date/quantity (`neededByDate`).
- `aesl:suppliesDelivery` — a `SupplyItem`/`JitNeed` satisfying a `Delivery`.
- Closed vocab `supplyStatus`: `in_stock`, `below_threshold`, `reorder`.
- Regenerate + validate (`run_validate_spec.sh`) in the same commit as any
  data-model change; never hand-edit generated TTL / enums.

## Build scope
- **B4 · Ledger** — on-hand qty per material; min-threshold + reorder state;
  material↔delivery link. Depends B2.
- **C2 · JIT** — store need-date/qty per job; below-threshold + near-need-date
  surfaces a suggested JIT delivery; scarcity auto-flag. Depends B4.
- **C3 · JIT × geofence** — arrival closes a JIT delivery at time-of-need. Depends C1, C2.

## Plan
1. Extend `data-model.md` with `supply_store.json` (items, on_hand, threshold)
   + a per-job `materials_need` map.
2. Warehouse/PM screens to view + adjust on-hand stock and thresholds.
3. JIT candidate logic: `below_threshold && within_need_date_window` → candidate.
4. JIT candidate becomes a scheduled delivery (spec 006 flow) with `suppliesDelivery`.

## Tasks
- [ ] `supply_store.json` shape + API (`/api/supply/*`) + data-model.md + ontology (B4).
- [ ] On-hand / threshold adjust UI (warehouse + PM) (B4).
- [ ] JIT candidate detection + scheduling hand-off (C2).
- [ ] Scarcity flag + email (C2).
- [ ] JIT geofence arrival close (C3).
- [ ] Ontology: `SupplyItem`, `JitNeed`, `supplyStatus` closed vocab; regenerate; gates green (C4).