# Spec 002 — Driver App: Plan & Tasks

## Plan
1. Reconcile with `001-server` (F4) so every screen's endpoints exist. Order:
   Incoming wizard → Ready to Pack → Send to PM → file serving → driver/mine auth.
2. Resolve the **no-Authorization-header** question: either attach the cached
   identity (`Bearer <email>` from `aes_cached_user`) to all fetches, or give the
   server a real session. Align with `004-auth`.
3. Validate `canvas.toBlob` on iOS/Android (README admits no real-device test).

## Tasks
- [ ] Enumerate every `fetch(...)` in `app.js` and cross-check against `contracts/api.md`; mark F4 hits.
- [ ] Attach identity to driver requests (with 004-auth).
- [ ] Confirm `canvas.toBlob` exists / add fallback `canvas.toDataURL`-derived Blob.
- [ ] Reconcile `file/<ticket_filename>` usage with server.
- [ ] On real device: camera, offline capture + queue, signature, geolocation, PWA install.
- [ ] Field-test the Incoming-Inventory wizard once server implements its contract.