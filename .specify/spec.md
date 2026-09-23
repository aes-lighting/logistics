# Spec Kit — AES Logistics

Version: `0.1.0` (spec-kit baseline; not yet tied to an external ontology).
Status: **scaffolded from HEAD survey. Build status lives in `builds/mvp-v1.md`.**

## Purpose

Single source of truth for what AES Logistics is, how it fits together, and
where the contract is broken at HEAD — so any agent or human works against the
real system, not the superseded README.

## Change control

- Any change to a live external-integration contract (auth-service, AES File
  Service, Twilio, Google Maps Distance Matrix, SMTP) updates the owning spec
  (`specs/007-integrations/`) in the **same commit** as the code.
- Any change to the **shared OCR regexes** updates `server/server_config.json`
  and the note in `specs/001-server/spec.md` together.
- Ontology/IRI/closed-vocab bumping: not applicable yet (no `.ttl` ontology in
  this kit). If one is introduced, adopt `.specify/ontology/` + `template_version`
  discipline and this section becomes mandatory.
- `counsel_approved` is a **forbidden** status here (no counsel role). Never
  mint it as a document status.

## Kit index

| Path | Role |
|---|---|
| `AGENTS.md` | Entry point / navigation + critical warnings |
| `.specify/product.md` | Product deep dive: actors, roles, flows |
| `.specify/architecture.md` | System architecture, components, data flow, integrations |
| `.specify/memory/project-context.md` | Ground truth about HEAD state & known drift |
| `.specify/builds/agent-playbook.md` | How agents should work in this repo |
| `.specify/builds/mvp-v1.md` | Build/verification state per subsystem |
| `specs/001-server/` | Flask API: routes, OCR, filing, static serving |
| `specs/002-driver-app/` | PWA: capture, IndexedDB queue, sync, roles |
| `specs/003-pm-portal/` | `/pm`: calendar, scheduling, tickets, admin, inventory |
| `specs/004-auth/` | Auth model: auth-service proxy + role decorators (incl. current weaknesses) |
| `specs/005-inventory/` | Incoming + Outgoing inventory, locations, Excel |
| `specs/006-scheduled-delivery/` | Ticket lifecycle: scheduled→packed→en_route→completed |
| `specs/007-integrations/` | SMTP, Twilio SMS, Google Maps, AES File Service, ICS |
| `specs/008-infra-ops/` | Docker, Railway, cloudflared, launcher, filesystem layout |
| `design/001-flows.md` | Screen map + end-to-end user flows |
| `ops/runbook.md` | Build, run, test, deploy |
| `ops/security.md` | Security findings & remediation (secrets, auth) |
| `ops/cron.md` | Scheduled jobs (reminders, daily report) |
| `templates/` | `.env.example`, `server_config.json` reference copies |

## Conventions

- Numbered specs `NNN-`: core (0xx), then features (1xx…). `contracts/` hold
  exact request/response and route tables.
- Data-model notes live in each spec's `data-model.md` (JSON stores are the
  persistence layer — no SQL).
- If a spec cites the central `.specify/` pool instead of its own `research.md`,
  that is by design, not a gap.