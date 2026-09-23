# Spec 010 — Geofencing

## Purpose
Give each delivery a geofence (center lat/lng + radius in meters) around its
site. The driver PWA triggers spatial events — **entry into** and **arrival
inside** the fence — which gate/automate delivery stage transitions and (with
spec 009) close JIT deliveries at time-of-need. MVP build C1 (device geo-trigger
+ data model), C3 (JIT closer).

## Ontology edge
- `aesl:Geofence` — a value object on a Delivery: `centerLatitude`,
  `centerLongitude`, `radiusMeters`.
- `aesl:hasGeofence` (Delivery → Geofence, at most one).
- Closed vocab `geofenceTrigger`: `en_route_entry`, `arrival` (distinct from
  the driver's manual "start" / "complete" buttons — the geometry is the signal).
- Regenerate + validate in the same commit; never hand-edit generated TTL/enums.

## Build scope
- **C1 · Geofence + device trigger** — `data-model.md` geofence fields;
  `aesl:Geofence` + `aesl:hasGeofence`; driver app geolocation loop emits
  en-route-entry/arrival when inside the fence. Depends A3, B4.
- **C3 · JIT close** — arrival event marks the JIT delivery's materials
  received (spec 009). Depends C1, C2.

## Plan
1. Add geofence to the scheduled delivery record (`center_lat`, `center_lng`,
   `radius_m`, set at scheduling when the PM picks a site; default from site geocode).
2. Driver app: watch geolocation; compute distance to center; emit `en_route_entry`
   when first entering radius, `arrival` when stopping inside after `en_route`.
3. Events POST to server (`/api/schedule/<id>/geofence`); server records the
   trigger and (Spec 009 C3) refreshes on-hand + closes JIT.
4. On-device test: fence change, entry/exit spam guard, offline buffering.

## Tasks
- [ ] Geofence fields on delivery record + PM site-pick/default (C1).
- [ ] `aesl:Geofence` + `aesl:hasGeofence` + `geofenceTrigger` closed vocab; regenerate; gates green (C4).
- [ ] Geolocation watch + distance calc + emit entry/arrival (C1).
- [ ] `/api/schedule/<id>/geofence` endpoint + trigger persistence (C1).
- [ ] JIT arrival close + on-hand refresh (C3).
- [ ] Device E2E: entry/arrival, spam guard, offline buffer (D1).