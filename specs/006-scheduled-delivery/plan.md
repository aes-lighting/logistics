# Spec 006 — Scheduled Delivery: Plan & Tasks

## Plan
1. Fix the three frontend↔server contract mismatches that block this flow end-to-end
   (`file/<…>`, `send_to_pm`, `already_scheduled`).
2. Stabilize driver identity key for assignment matching.
3. Add an E2E test harness (README already has manual E2E claims; codify into a
   test script) covering: schedule→ticket→pack→start→complete, + revision at each stage.

## Tasks
- [ ] WS-4 file-serving alignment.
- [ ] `/send_to_pm` ↔ `/send_copy_to_pm` alignment (server or client).
- [ ] `already_scheduled` in `/api/schedule/calendar/upcoming`.
- [ ] `assigned_driver` identity decision + matching test.
- [ ] E2E script: full lifecycle incl. revision-reset and revision-en_route.
- [ ] Emails: PM+receiver on complete; PM+warehouse-alert on revise; verify attachments.