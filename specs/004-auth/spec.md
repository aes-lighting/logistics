# Spec 004 — Auth

## Purpose
Document the auth model at HEAD and the gap that must be closed before this is
safe for real production use.

## Model (HEAD)
Login **proxies** to an external **auth-service** microservice:
- `POST /api/auth/login` → `verify_auth_with_service()` → auth-service returns
  `{user_id?, email, name, role}` (role one of `driver`, `pm`, `admin`).
- The client stores this in `localStorage` (`aes_cached_user`) and presents it as
  `Authorization: Bearer <email>` on later calls (PM portal does; driver app mostly
  doesn't attach anything).

### ⚠️ Security gap (F3) — the server trusts an unverified string
`auth_decorators.py`:
- `login_required` / `admin_required` / `pm_or_admin_required` each check only
  that `get_auth_header()` returned **a non-empty string** (a bare email from the
  header). They do **not** call auth-service to validate the token or the role.
- `get_auth_header()` (`auth_utils.py`) just strips `Bearer ` and returns the
  remainder — no signature, no expiry, no lookup.

Net effect: **any caller who sends `Authorization: Bearer anything@foo.com` is
treated as logged-in with whatever the stub role gate implies**. Admin/PM
endpoints (`/api/auth/admin/*`, `/api/schedule*` pm_or_admin, `/api/inventory/export`,
`/api/inventory/<id>/remove`, `/api/schedule/<id>` DELETE) are gated only by header
presence ⇒ privilege escalation and impersonation are trivial at the API layer.
The README's description of a "signed cookie, 30 days" session is **not what the
code does** at HEAD.

## Target state
Role- and identity-verified requests:
- On each privileged call, validate the presented identity **with auth-service**
  (e.g. `GET /api/auth/me` or a token-info call) before granting pm/admin actions.
- Or move to short-lived signed tokens (JWT/HMAC) with expiry + server-side
  validation, keeping the driver-PWA offline flow in mind.
- Driver app must attach identity consistently (002-plan) so `@login_required`
  calls are actually distinguishable.
- Admin tools scoped by verified role, not header presence.

## Contracts / tasks
- Map decorators → each protected route in `contracts/api.md`.
- Tasks live in `plan.md`.