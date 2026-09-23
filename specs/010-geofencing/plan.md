# Spec 010 — Geofencing: Plan & Tasks

## Plan
1. **Data model (C1):** geofence on the delivery record; `aesl:Geofence` +
   `aesl:hasGeofence` + closed `geofenceTrigger`; docs in `data-model.md`.
2. **Device (C1):** navigator geolocation watch; haversine to center; emit
   `en_route_entry` (first crossing into radius) → `arrival` (inside after
   en_route). Guard against entry/exit spam; buffer when offline.
3. **Server (C1):** `/api/schedule/<id>/geofence` persists triggers; 401 auth
   via spec 004 path.
4. **JIT closer (C3):** arrival handler calls spec 009 on-hand refresh +
   JIT close.
5. **E2E (D1):** real-device fence change, spam guard, offline buffer.

## Tasks
- [ ] C1: geofence fields + PM site pick / default geocode.
- [ ] C4: ontology `Geofence`/`hasGeofence`/`geofenceTrigger`; regenerate; gates green.
- [ ] C1: geolocation watch + haversine + entry/arrival emit + spam guard + offline buffer.
- [ ] C1: `/api/schedule/<id>/geofence` + persistence.
- [ ] C3: arrival → JIT close + on-hand refresh.
- [ ] D1: device E2E (fence change, spam, offline).