# Spec 001 — Server API: Tasks

- [ ] WS-4 File-serving path — decide `file/<name>` vs `file/<int>`; align app.py + frontend + contracts.
- [ ] WS-1 Add wizard endpoints (with 005-inventory): `scan_page`, `confirm_job`, `pallet_photo`, `finalize`, `inventory/pms`, `warehouse/ready_to_pack`.
- [ ] WS-1 Wire wizard → `inventory.py` ledger + QR + mark-shipped-on-pack.
- [ ] WS-3 `/api/upload` sync — confirm/implement ad-hoc mirroring or local-only filing; document.
- [ ] WS-2 Fix `send_daily_inventory_report.py` to use auth-service admin/users (drop `import auth`).
- [ ] WS-5 Implement real role checks in `auth_decorators.py` (coordinated with 004-auth).
- [ ] WS-6 Remove `auth_store.json` from docker-compose; prune stale root `.env.example`.
- [ ] Add a real test suite (import smoke test is not enough).
- [ ] Update `contracts/api.md` to match final routes.