# Spec 004 — Auth: tasks

- [ ] Choose validation scheme (JWT vs per-request echo) — decision record here.
- [ ] Implement role verification in decorators against auth-service.
- [ ] Driver app attaches identity on all authenticated calls.
- [ ] 401 → re-login flow + stale-cache eviction.
- [ ] Decorator unit tests (allow/deny-role/deny-none).
- [ ] Document TTL + revocation.