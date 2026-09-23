# Spec 007 — Integrations: Plan & Tasks

## Plan
1. Stop the secret leak (F2): `AES_API_KEY`/`AES_API_URL` from env only; remove
   hardcoded default in `app.py`; verify with `env -i` run.
2. Decide ad-hoc mirror behavior; document in `001/contracts/api.md`.
3. Add sentinel tests so each integration provably degrades gracefully.

## Tasks
- [ ] Remove hardcoded AES defaults; read from env (F2).
- [ ] Decide + implement ad-hoc ( `/api/upload` ) AES mirror or document local-only.
- [ ] Sentinel tests (each integration, env unset → expected return).
- [ ] Review auth-service timeout/503 handling in `api_schedule_*` pms/drivers.