# Spec 009 — Supply/JIT tasks

- [ ] B4: `supply_store.json` + `/api/supply/*` + adjust UI (warehouse + PM).
- [ ] C4: ontology `SupplyItem` / `JitNeed` / `suppliesDelivery` / `supplyStatus`; regenerate; gates green.
- [ ] C2: JIT candidate detection (below-threshold ∧ within need-date window).
- [ ] C2: JIT candidate → scheduled delivery hand-off.
- [ ] C2: scarcity flag + email.
- [ ] C3: geofence arrival closes JIT; on-hand refresh.
- [ ] Tests: threshold flip, window math, JIT→schedule, geofence close.