# AGENTS.md

This repo is governed by a **Spec Kit** (speckit). Before changing code, read the kit so you build against the system as it actually is — not as the README describes it. The README documents an **older, superseded** architecture on several axes (see §3).

---

## 1. What this is

AES Logistics is a delivery-photo + inventory system for AES Lighting Group:

- **`driver_app/`** — installable PWA (phones). Offline photo capture of ticket + pallet, end-of-shift sync; plus Warehouse (Incoming/Outgoing inventory) and the schedule/delivery flows.
- **`pm_portal/`** — desk/laptop UI at `/pm` for PMs + admins: calendar sync, scheduling, ticket upload/generate, admin tools, inventory & Excel export.
- **`server/`** — single Flask app serving all three (static files + JSON API). OCR (Tesseract) reads job/PO numbers. Integrates with external auth, AES File Service, SMTP, Twilio, Google Maps, ICS calendar.

## 2. Repo map

```
AGENTS.md                 ← you are here (kit entry)
.specify/                 ← product/architecture/spec index/build/memory
specs/                    ← numbered subsystem specs (spec/plan/tasks/data-model/contracts)
design/                   ← UX flows, screen map
ops/                      ← runbook, security, cron
server/                   ← Flask app + modules          (Python 3.9+, Tesseract)
driver_app/               ← PWA (vanilla JS, IndexedDB)
pm_portal/                ← PM Portal (vanilla JS)
Dockerfile / docker-compose.yml / railway.json / start.sh / AES_Logistics_Launcher.bat
.env.example  .gitignore
```

## 3. ⚠️ Read these FIRST — the kit's explicit warnings

0. **Ontology contract.** `.specify/ontology/` is a JSON-driven domain ontology
   (`aesl:` namespace) gated by `.specify/scripts/run_validate_spec.sh`
   (contract + SHACL + OWL-RL). It reflects the *real* HEAD code and `data-model.md`,
   not the README. **Read it before changing the data model or inventory/
   scheduling semantics**, and regenerate + re-validate after any such change.
1. **Docs/app drift.** `README.md`, `.env.example`, `docker-compose.yml` describe an **embedded, shared-password auth** (`auth.py`, `auth_store.json`, `SHARED_PASSWORD`). That model was **removed** in commit `8c92283` and replaced by an external **auth-service microservice** on Railway. Treat README auth/config/docker text as stale unless it matches what you see in `.specify/` and `server/*.py`.
2. **Contract drift (frontend ↔ server).** The frontends call endpoints `server/app.py` does **not** implement at HEAD: the session-based Incoming Inventory wizard (`/api/incoming/scan_page|confirm_job|pallet_photo|finalize`, `/api/inventory/pms`, `/api/schedule/warehouse/ready_to_pack`, `/send_to_pm`, `file/<ticket_filename>`) vs. server's single-shot `/api/incoming/scan|confirm|flag` + `/send_copy_to_pm` + `file/<int>`. Mapping table in `specs/001-server/contracts/api.md`. Do not "fix" one side without the other.
3. **Broken script.** `server/send_daily_inventory_report.py` does `import auth` + `auth.list_users()` — that module was deleted. The daily report script **crashes at import**. See `ops/cron.md`.
4. **Secrets.** `.env` (real values incl. API keys) is **still git-tracked at HEAD** and `server/app.py:93` hardcodes a real `AES_API_KEY` fallback. See `ops/security.md` — this must be remediated.

## 4. Rules

- Ground every claim in HEAD's code (`server/*.py`, `driver_app/app.js`, `pm_portal/app.js`), not the README.
- Never modify an external integration (auth-service, AES File Service, Twilio, Google Maps, SMTP) contract without updating `specs/` first.
- Keep `server_config.json` patterns as the single source for OCR regexes; tune against real slips/tickets before touching them.
- Don't bump ontology/`template_version`/`content_hash` values unless the change-control rules in `.specify/spec.md` say so.
- Never place secrets in code or config; `ops/security.md` lists the known leeks to purge.

## 5. Spec Kit (speckit) section

Structure and conventions: `.specify/spec.md` (index), `.specify/product.md`, `.specify/architecture.md`, `.specify/memory/project-context.md`, `.specify/builds/{agent-playbook,mvp-v1}.md`, `specs/NNN-*/` (each: `spec.md`, `plan.md`, `tasks.md`, plus `data-model.md`/`contracts/` where topical), `design/`, `ops/`. Later specs cite the central `.specify/` pool rather than duplicating it.

**Domain ontology** (`.specify/ontology/` + `.specify/scripts/`): `aesl:` namespace, JSON-driven (no SQL). See `.specify/ontology/README.md`. Validate with `.specify/scripts/run_validate_spec.sh`. Guidelines: never hand-edit generated TTL/enum files; regenerated artifacts must be committed in the same commit as the source change; an agent must never auto-complete a delivery or fabricate signatures/photos/geotags (`aesl:PolicyNoAutoCompletesDelivery`).

**MVP roadmap** (`.specify/builds/mvp-roadmap.md`): the MVP definition — auth, add-users, take-in deliveries, schedule deliveries, supply/materials, JIT, geofencing — broken into Phases A–D and independently-assignable Builds (A1…D3) with explicit dependencies for parallel small-team execution. Specs 009 (supply/JIT) and 010 (geofencing) carry the new MVP work; 004/005/006 carry the core-loop closure. Follow the roadmap's guid: contract reconciliation (A3) unblocks every functional track, so schedule it early and lock it.