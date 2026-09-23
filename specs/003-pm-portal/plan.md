# Spec 003 — PM Portal: Plan & Tasks

## Plan
1. Closing the three open questions above (role gate, driver-name keying, already_scheduled).
2. Ensure admin UI actions map 1:1 to server endpoints (register/list/delete) —
   verify role scoping actually enforced at server (with 004-auth).
3. Driver-name identity: prefer matching by registered email/name token to keep
   assignment stable when display names change.

## Tasks
- [ ] Verify server enforces pm/admin on register/delete/export (004-auth WS-5).
- [ ] Decide driver identity key (name vs email) and align `scheduling.assigned_driver`.
- [ ] Resolve `already_scheduled` derivation (server vs client).
- [ ] Cross-check every `api()` call vs `contracts/api.md`; mark F4 rows.
- [ ] Add server-side tests for schedule CRUD + view payload.