# Agent Playbook — working in AES Logistics

How to operate safely and truthfully in this repo.

## Before you start

1. Read `AGENTS.md` (warnings F1–F6) and `.specify/memory/project-context.md`.
2. Verify the actual HEAD state yourself — do not trust this doc or the README
   alone. The contract-drift table (`specs/001-server/contracts/api.md`) tells
   you what to re-check.
3. If a task touches auth, the AES File Service, or any external integration,
   read `specs/004-auth/` and `specs/007-integrations/` first.

## Grounding rules

- **Code is truth; README is memory.** Quote `server/*.py` / `app.js` line
  references when asserting behavior, not README claims.
- **Never "fix" one side of a contract.** A route change without the matching
  frontend change (or vice versa) is how F4 was born. If you align an endpoint,
  update `specs/001-server/contracts/api.md` in the same commit.
- **Never hardcode secrets.** If you find a missing `.env` value, reference the
  key name, don't paste a value. Follow `ops/security.md` to purge F1/F2.
- **Failing smoke test?** Run `server/test-app.py` (imports all modules +
  `/api/health`) to isolate a broken import from a logic bug. Remember
  `send_daily_inventory_report.py` is known-broken (F5) — don't "fix" the
  report by re-adding `auth.py`; use the auth-service admin/users call.

## Workflow

1. Branch from `main`.
2. Make the change against the spec (`specs/NNN-*`).
3. Update the owning spec (`specs/`, `contracts/`) in the same commit.
4. Add/verify tests. There is **no test suite** beyond `test-app.py` (an import
   smoke test) — you are expected to hand-run flows or add real tests.
5. Commit clearly; reference the spec dir.

## Pitfalls

- **Empty-path reads / re-reading files** loop and burn tokens — use grep sweeps
  and read targeted ranges.
- **Trusting `.env.example` / compose** for what the app *actually uses* — verify
  against `os.environ.get(...)` calls in code.
- **Invoking the daily report script** expecting it to work — it raises at import (F5).
- **Running Docker** with the legacy `auth_store.json` mount — harmless but inert;
  don't assume `/app/server/auth_store.json` is written.
- **`.gitignore` trailing space** — any edit to ignore rules must verify with
  `git check-ignore -v .env` (should now be untracked-able) and `git rm --cached`.

## Definition of done

- Change is in code **and** in the owning spec/contract.
- No secret added; `.env` remains untracked or purged per `ops/security.md`.
- `python3 server/test-app.py` passes (imports + health).
- Smoke-tested the touched flow (hand curl, or browser against a local server).