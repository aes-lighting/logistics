# Ops — Security

**Read `001-server/contracts/api.md` + `004-auth` first.** These are the live
weaknesses found at HEAD; they must be remediated before this code gets wider
distribution, real production data, or any third-party/outside access.

## Findings (from HEAD survey)

### F1 — `.env` with real secrets is still git-tracked
`git ls-files` shows `.env` (and `.env.example`, `server/.env.example`). The tip
commit message ("Stop tracking .env file for security") is **false** — the file
is still in the index. `.gitignore` has a **broken rule with a trailing space**
(`.env ` / `**\.env `) so `git check-ignore .env` matches nothing.

**Remediate:**
```bash
git rm --cached .env           # keep working copy, stop tracking
# fix .gitignore: replace the trailing-space line with:
#   .env
#   .env.*
#   !.env.example               (if you want examples tracked)
git add .gitignore server/.env.example .env.example
git status && git check-ignore -v .env   # must NOT be tracked
git commit -S -m "Untrack .env and fix broken .gitignore (secrets no longer tracked)"
```
Then **rotate** every exposed secret that was committed in history (they're in
git history even after untrack): AES_API_KEY, FLASK_SECRET_KEY, SMTP/Twilio/Google
creds, ADMIN_EMAIL/PASSWORD. Treat the old AES_API_KEY as compromised.

### F2 — Hardcoded API key in source
`server/app.py:92-93` defaults `AES_API_URL=http://71.172.107.128:3001` and
`AES_API_KEY=<64-char real key>` when env is unset. Remove both defaults; fail
fast or warn if `AES_API_KEY` is missing (never ship a fallback secret).

### F3 — Auth role/identity trust gap (critical)
Role decorators (`auth_decorators.py`) only check that an `Authorization:
Bearer <email>` string is present; they do **not** verify it with auth-service.
Effect: **any string authenticates as that user; admin/PM gating is effectively
header-presence only** → impersonation + privilege escalation at the API layer.
The README's claim of a "signed 30-day cookie" is not what the code does.
→ `specs/004-auth` plan (verify identity+role server-side per privileged request;
attach identity on driver calls; token TTL + re-login).

### F4 — Contract mismatch (not a vuln, but a correctness/availability bug)
Frontend calls endpoints the server doesn't implement (404s). Not a secret
leak, but a live functional break. → `001/005` plan.

### F5 — Broken cron script (availability)
`send_daily_inventory_report.py` imports deleted `auth` → crash. → `001-WS-2`.

### F6 — Legacy/inert references
`auth_store.json` mount, root `.env.example` legacy keys. Low risk, clean up.

## Hardening checklist (proposed)
- [ ] Purge F1/F2; rotate leaked creds.
- [ ] Implement F3 fix (#004-auth) w/ tests.
- [ ] Enforce HTTPS at proxy (PWA requirement); HSTS.
- [ ] Restrict CORS/origins; validate filenames on upload (path traversal).
- [ ] Rate-limit login + upload; cap upload sizes.
- [ ] Scan headers vs static catch-all (`<path:filename>`) for traversal.
- [ ] Add CI secret scanning (gitleaks/trufflehog) on push.
- [ ] Pre-commit hook: block `.env`/`*.pem`/keys.
- [ ] Rotation policy + key management (env-only), documented in `SPEC/007`.