# Spec 001 — Server API: Contracts (live route table)

**Legend:** ✅ implemented at HEAD (`server/app.py` / `auth_routes.py`)
· ❌ called by frontend but **NOT implemented** at HEAD · ⚠️ present but behavior differs.

## Auth

| Method & path | Impl | Notes |
|---|---|---|
| POST `/api/auth/login` | ✅ | proxy → auth-service; body `{email,password}`; returns `{role,name,email}` |
| POST `/api/auth/logout` | ✅ | clears nothing server-side; returns `{status:"ok"}` |
| GET `/api/auth/me` | ✅ | echoes `Authorization: Bearer <email>` (no token validation — F3) |
| POST `/api/auth/admin/register_user` | ✅ | proxied; body `{name,email,role}` |
| GET `/api/auth/admin/users` | ✅ | proxied; returns `{users:[{user_id,name,email,role}]}` |
| DELETE `/api/auth/admin/users/<int:user_id>` | ✅ | proxied |

## Health / static

| Method & path | Impl | Notes |
|---|---|---|
| GET `/api/health` | ✅ | `{status:"ok",service,timestamp}` |
| GET `/` | ✅ | driver PWA |
| GET `/pm` | ✅ | PM portal |
| GET `/<path:filename>` / `/pm/<path>…` | ✅ | static |

## Ad-hoc delivery

| Method & path | Impl | Notes |
|---|---|---|
| POST `/api/upload` | ❌ **no handler at HEAD** | driver `app.js` posts multipart (metadata + photos). Decide/implement (WS-3). |

## Scheduled delivery

| Method & path | Impl | Notes |
|---|---|---|
| GET/POST `/api/schedule/calendar/settings` | ✅ | `{settings:{ics_url}}` / `{ics_url}` |
| GET `/api/schedule/calendar/upcoming` | ✅ | `{events:[{uid,title,start_iso, (client adds already_scheduled)}]}` — server does **not** add `already_scheduled`; client derives? **⚠️ verify**
| GET `/api/schedule` | ✅ | `{deliveries:[…]}` |
| POST `/api/schedule` | ✅ | requires job_number,receiver_name,receiver_email,receiver_phone,site_address,assigned_driver,pm_email,delivery_date |
| POST `/api/schedule/<id>/ticket` | ✅ | multipart `ticket` OR `generate_ticket=true`+`line_items` JSON |
| POST `/api/schedule/<id>/generate_ticket` | ✅ | `{line_items}` → renders + saves generated ticket |
| POST `/api/schedule/<id>/revise_ticket` | ✅ | `{line_items}` or header fields |
| GET `/api/schedule/<id>/file/<n>` | ✅ | `<n>` = `"ticket"`, int index (photos then signature), **or a stored filename** (`ticket_filename`, photo, `signature_filename`, `packed_signature_filename`) — what both frontends send. Only filenames recorded on the delivery are served. Unauthenticated (used as `<img src>`; F3/spec 004). |
| POST `/api/schedule/<id>/pack` | ✅ | `packed_by`, `signature`, `line_item_checks` JSON or `checkoff_confirmed=true`; requires all items when line_items present |
| POST `/api/schedule/<id>/start` | ✅ | `{latitude,longitude}`; SMS + ETA; returns `{sms_sent,sms_error,eta}` |
| POST `/api/schedule/<id>/complete` | ✅ | `signed_by`, `signature`, `photos`(≥2), `geotag`, `unload_item_checks`/`checkoff_confirmed`; emails PM+receiver; mirrors to AES File Service (`delivery_photo`); response adds `file_service:{success,uploaded,failed}` |
| POST `/api/schedule/<id>/send_copy_to_pm` | ✅ | PM portal; `@pm_or_admin_required`; `{pm_email}` → `{status, sent}` (`sent` added — PM portal checks it). |
| POST `/api/schedule/<id>/send_to_pm` | ✅ | driver app Warehouse; `@login_required`; same handler/response as above. |
| DELETE `/api/schedule/<id>` | ✅ | deletes record + files |
| GET `/api/schedule/pms` | ✅ | client calls this (`/api/schedule/pms`) — filtered to pm/admin |
| GET `/api/schedule/drivers` | ✅ | `{drivers:[{name}]}` |
| GET `/api/schedule/driver/today` | ✅ | `{deliveries}` ready today |
| GET `/api/schedule/driver/mine` | ✅ | **`?driver_name=`** required; driver's packed/en_route list |
| GET `/api/schedule/warehouse/ready_to_pack` | ✅ | `@login_required`; `{deliveries}` = `scheduling.deliveries_ready_to_pack()` (status `ticket_uploaded`, by date) |

## Inventory (pm)

| Method & path | Impl | Notes |
|---|---|---|
| GET `/api/inventory/locations` | ✅ | `{locations:[13]}` |
| GET `/api/inventory` | ✅ | `{entries:[…]}` (active only) |
| POST `/api/inventory/<id>/remove` | ✅ | Mark Shipped |
| GET `/api/inventory/export` | ✅ | XLSX (pm/admin) |
| GET `/api/inventory/pms` | ✅ | see wizard table below |

## Incoming inventory — wizard (sanctioned contract; A3, landed 2026-09-23)

Session state is on disk at `<incoming_staging_dir>/<session_id>/session.json`
(+ `page_N.jpg`, `pallet_N.jpg`) so it works across gunicorn workers. All routes `@login_required`.

| Method & path | Impl | Notes |
|---|---|---|
| POST `/api/incoming/scan_page` | ✅ | multipart `photo` (or `slip`), `session_id?` → `{session_id, page_count, job_number_guess, po_number_guess}`. No `session_id` opens a session; first page with a match sets each guess. |
| POST `/api/incoming/confirm_job` | ✅ | `{session_id, job_number, po_number?, staff?, pm_email?}` → `{session_id, pm_email}`. `pm_email` given → memoized in `job_pm_directory`; else looked up; neither → **400 `{"error":"needs_pm"}`**. |
| POST `/api/incoming/pallet_photo` | ✅ | multipart `session_id`, `photo` → `{pallet_photo_count}`. Requires confirmed session (409 otherwise). |
| POST `/api/incoming/finalize` | ✅ | `{session_id, pallet_count, locations:[{location,count}], comment?}` → `{entry, qr_pdf_url, email_sent, email_error, file_service}`. **Server gates:** photos ≥ pallet_count; every location ∈ `inventory.LOCATIONS`; counts ≥1 and **sum == pallet_count** (400 otherwise). Files pages + pallet photos to `<dest_dir>/Incoming_Packing_Slips/Job_<n>/`, writes ledger entry, QR PDF, emails PM (slip pages + QR attached), mirrors pages (`packing_slip`) + pallet photos (`intake_photo`) to the AES File Service, deletes session. |
| POST `/api/incoming/flag` | ✅ | wizard `{session_id, reason, note?, staff?}` (flags all pages) **or** legacy `{slip_id, reason}` → `{email_sent, email_error}`. |
| GET `/api/inventory/<id>/qr.pdf` | ✅ | printable QR receiving label (`qr_pdf_url` from finalize). |
| GET `/api/inventory/pms` | ✅ | `{pms:[{name,email}]}` — auth-service pm/admin users; falls back to emails in `job_pm_directory` if auth-service refuses/unreachable. |

## Incoming inventory — legacy single-shot (kept, not called by frontends)

| Method & path | Impl | Notes |
|---|---|---|
| POST `/api/incoming/scan` | ✅ | multipart `slip` → `{slip_id, job_number, po_number}` |
| POST `/api/incoming/confirm` | ✅ | `{slip_id, job_number, po_number}`; files slip + `inventory.add_entry` (previously called non-existent `inventory.log_packing_slip` → 500; fixed). |

## Decision (owner: 005-inventory) — DONE
Aligned on the **wizard contract** (extended server). Driver app now attaches
`Authorization: Bearer <email|name>` on same-origin `/api/` calls (global fetch
wrapper), matching the PM portal — without it every `@login_required` route
returned 401 to the driver app. This is the same unverified-identity scheme
as the PM portal; F3 (spec 004) still applies.
