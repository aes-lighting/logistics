# MVP Roadmap — AES Logistics (Phase/Build/Task breakdown)

**Scope (MVP definition):** user authentication · add users · take-in
deliveries · schedule deliveries · supply/materials management · just-in-time
(JIT) deliveries · geofencing.

**Mode:** small team working in parallel under calendar/time constraints. Every
`Build` below is an independently assignable unit of work. Dependencies are
explicit; two builds with the same `Depends` run concurrently.

**Gating:** all work complies with the spec kit + ontology principles
(`.specify/spec.md`, `.specify/ontology/README.md`). Any data-model / semantics
change must regenerate snapshots + TTL and pass `run_validate_spec.sh` (contract
+ SHACL + OWL-RL) **in the same commit**. Never hand-edit `*.generated.ttl` or
`*.shacl.enums.ttl`. Agents never auto-complete deliveries or fabricate
signatures/photos/geotags (`aesl:PolicyNoAutoCompletesDelivery`).

---

## Phase A — Foundation (unblocks all downstream tracks)

| Build | Tasks | Dev track | Depends |
|---|---|---|---|
| **A1 · Secret purge** | (1) `git rm --cached .env`; rotate every leaked secret (esp. `AES_API_KEY` — it is in git history twice); (2) fix `.gitignore` (broken `.env ` trailing-space rule + missing `.venv/`); (3) remove hardcoded `AES_API_KEY` default in `app.py`; (4) confirm no secret in `git grep` | Ops/security | — |
| **A2 · Auth gate close** | spec 004: real token validation against auth-service; role checks in decorators (deny wrong role, deny none); 401 → re-login + stale-cache eviction; add-user admin endpoints (`/api/admin/users`) with role list {driver, warehouse, pm, admin}; TTL + revocation docs | Auth | A1 |
| **A3 · Contract reconciliation** | spec 001 F4: implement server routes the frontends already call — Incoming wizard (`scan_page`, `confirm_job`, `pallet_photo`, `finalize`), `/api/inventory/pms`, `/api/schedule/warehouse/ready_to_pack`, `/send_to_pm`, `file/<ticket_filename>`; align `001-server/contracts/api.md` | API | — |
| **A4 · CI gates** | GitHub Actions: run `run_validate_spec.sh` + a server smoke test on push/PR to `main`; make ontology drift a red gate | Infra | A1 |

**Milestone A:** secrets out of history, auth actually authenticates, frontend↔server agree, gates are green and enforced.

---

## Phase B — Core operations (parallel tracks; biggest win for parallelizing)

| Build | Tasks | Dev track | Depends |
|---|---|---|---|
| **B1 · Add users** | A2 user endpoints wired to PM Portal admin UI: create/disable/list driver/warehouse/PM accounts; role-gate admin calls per spec 003 | Auth | A2 |
| **B2 · Take-in deliveries** | spec 005: Incoming wizard E2E (scan slip → confirm job/PO via OCR → pallet photos → split locations → finalize → QR PDF → auto-email PM). Fix `send_daily_inventory_report.py` `import auth` crash (F5) | API/PWA | A3 |
| **B3 · Schedule deliveries** | spec 006: calendar sync → setup → ticket upload/generate → Ready-to-Pack → pack/checkoff/sign → driver list → en-route (ETA) → complete (photos+signature+geotag) → email PM+receiver; fix `already_scheduled`, `file/<…>`, `send_to_pm` | API/Sched | A3 |
| **B4 · Supply/materials ledger** | NEW (spec 009): track on-hand quantities per material (linked to inventory entries + jobs); min-threshold + reorder state; material↔delivery link (`aesl:suppliesDelivery`) | Inventory | B2 |

**Milestone B:** users exist, deliveries are taken in and scheduled E2E, and supply quantities are tracked.

---

## Phase C — MVP differentiators (the new capabilities)

| Build | Tasks | Dev track | Depends |
|---|---|---|---|
| **C1 · Geofencing** | NEW (spec 010): per-delivery/geofence (center lat/lng + radius); driver app geo-triggers en-route-entry & arrival events; geofence fields in `data-model.md` + `aesl:Geofence` class | PWA/Geo | A3, B4 |
| **C2 · JIT deliveries** | NEW (spec 009): store materials-need date/quantity per job; when below-threshold + need-date approaches, surface a **JIT delivery** (suggested schedule); auto-flag material scarcity | Scheduling | B4 |
| **C3 · JIT × geofence** | arrival geofence event closes a JIT delivery (marks material received at time-of-need); ops dashboard shows JIT status | Integ | C1, C2 |
| **C4 · Ontology + gates update** | `SupplyItem`, `JitNeed`, `Geofence` classes + `supplyStatus`/`geofenceTrigger` closed vocabs; regenerate + validate (own the diff) | Ontology | B4–C2 (alongside) |

**Milestone C:** the app knows *where* deliveries are (geofence), *what* materials are needed and *when* (JIT), and closes the loop on arrival.

---

## Phase D — Hardening → MVP go-live

| Build | Tasks | Dev track | Depends |
|---|---|---|---|
| **D1 · E2E acceptance** | Installable PWA on real device: offline capture→sync, camera, black-signature pad, geotag; Incoming + Schedule + JIT + geofence happy paths; the 2 SHACL rejects as real device cases | QA | B2–C3 |
| **D2 · Ops close-out** | fix all broken cron scripts; runbook/monitoring/capacity (single-instance JSON is not cluster-safe — document); Railway/Docker verified | Ops | all |
| **D3 · Go-live** | MVP checklist: secrets rotated & clean, auth live, all 6 capabilities demonstrable, ontology gates green in CI, docs final | Docs/PM | D1–D2 |

**Milestone C = MVP gate.** All six capabilities demonstrable:

1. **User authentication** — real login, role checks.
2. **Add users** — admin manages the user list.
3. **Take-in deliveries** — Incoming Inventory wizard E2E.
4. **Schedule deliveries** — scheduled-delivery lifecycle E2E.
5. **Supply/materials management** — on-hand quantities, thresholds, reorder.
6. **JIT deliveries** — need-date-driven scheduling.
7. **Geofencing** — arrival/entry triggers.

> *Seven capabilities* — auth, add-users, take-in, schedule, supply/materials,
> JIT, geofencing. JIT + geofencing are the differentiators; the rest are the
> core loop the product already half-builds.

## Sequencing for a small team

- **Tracks in parallel:** (A1→A4) ops/infra, (B1) auth, (B2/B3) API/PWA + sched, (B4/C1/C2) inventory + geo + JIT.
- **Ontology work is always adjacent** to B4/C1/C2 content changes (same feature branch, same commit).
- **A3 is the shared dependency** — every functional track needs the contract reconciled first, so schedule A3 early and lock it.