# Spec 004 — Auth: Plan & Tasks

## Recommended approach
Introduce a real validation step without a hard rewrite:
1. Add an auth-service endpoint already used by admin listing — but for a
   session, add `POST /api/auth/session/verify` (echo role) or reuse `GET /me`
   against the service. **Decision:** verify identity+role server-side per
   privileged request; cache negative/positive TTL to limit round-trips.
2. Change decorators to call validation; keep `@login_required` for identity-only
   routes (driver reads) and `@pm_or_admin_required`
   `@admin_required` to require the corroborated role.
3. Have the driver app attach `Authorization: Bearer <email>` to all calls.
4. Add expiry: auth-service token TTL → 401 → client re-login.

## Tasks
- [ ] Decide validation endpoint / token scheme (JWT vs per-request echo).
- [ ] Implement `@login_required/@pm_or_admin_required/@admin_required` role checks via auth-service.
- [ ] Attach `Bearer <email>` in driver app fetches.
- [ ] Evict stale `aes_cached_user`; handle 401 re-login.
- [ ] Unit-test decorators (allow, deny wrong role, deny missing).
- [ ] Document token TTL + revocation behavior in this spec.