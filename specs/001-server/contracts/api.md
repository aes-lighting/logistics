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
| GET `/api/schedule/<id>/file/<n>` | ⚠️ | server: `<n>` = `"ticket"` or **int index** → photos then signature. Frontend sends `file/<ticket_filename>` → **mismatch (F4)** |
| POST `/api/schedule/<id>/pack` | ✅ | `packed_by`, `signature`, `line_item_checks` JSON or `checkoff_confirmed=true`; requires all items when line_items present |
| POST `/api/schedule/<id>/start` | ✅ | `{latitude,longitude}`; SMS + ETA; returns `{sms_sent,sms_error,eta}` |
| POST `/api/schedule/<id>/complete` | ✅ | `signed_by`, `signature`, `photos`(≥2), `geotag`, `unload_item_checks`/`checkoff_confirmed`; emails PM+receiver; mirrors AES |
| POST `/api/schedule/<id>/send_copy_to_pm` | ✅ | `{pm_email}`; emails ticket copy. **Frontend calls `/send_to_pm` → mismatch (F4)** |
| DELETE `/api/schedule/<id>` | ✅ | deletes record + files |
| GET `/api/schedule/pms` | ✅ | client calls this (`/api/schedule/pms`) — filtered to pm/admin |
| GET `/api/schedule/drivers` | ✅ | `{drivers:[{name}]}` |
| GET `/api/schedule/driver/today` | ✅ | `{deliveries}` ready today |
| GET `/api/schedule/driver/mine` | ✅ | **`?driver_name=`** required; driver's packed/en_route list |
| GET `/api/schedule/warehouse/ready_to_pack` | ❌ **no handler** | frontend calls; `scheduling.deliveries_ready_to_pack()` exists but unexposed (WS-1) |

## Inventory (pm)

| Method & path | Impl | Notes |
|---|---|---|
| GET `/api/inventory/locations` | ✅ | `{locations:[13]}` |
| GET `/api/inventory` | ✅ | `{entries:[…]}` (active only) |
| POST `/api/inventory/<id>/remove` | ✅ | Mark Shipped |
| GET `/api/inventory/export` | ✅ | XLSX (pm/admin) |
| GET `/api/inventory/pms` | ❌ **no handler** | frontend + warehouse "Send to PM" call it (WS-1) |

## Incoming inventory (server single-shot)

| Method & path | Impl | Notes |
|---|---|---|
| POST `/api/incoming/scan` | ✅ | multipart `slip`; returns `{slip_id, job_number, po_number}` |

wait: config key is `incoming_staging_dir`; slip_id = basename of staged `uuid.jpg`.

| POST `/api/incoming/confirm` | ✅ | `{slip_id, job_number, po_number}`; moves to Incoming_Packing_Slips, logs entry |
| POST `/api/incoming/flag` | ✅ | `{slip_id, reason}`; moves to flagged; emails PMteam |

## Incoming inventory (**frontend wizard** — server mismatch F4)

| Method & path | Impl | Notes |
|---|---|---|
| POST `/api/incoming/scan_page` | ❌ | wizard expected `{session_id, photo?/slip?}` → `{session_id, job_number_guess, po_number_guess}` (frontend sends `photo`) |
| POST `/api/incoming/confirm_job` | ❌ | `{session_id, job_number, po_number, staff, pm_email?}`; `needs_pm` error |
| POST `/api/incoming/pallet_photo` | ❌ | `{session_id, photo}` |
| POST `/api/incoming/finalize` | ❌ | `{session_id, pallet_count, locations, comment}` → `{qr_pdf_url}` |
| POST `/api/incoming/flag` | ⚠️ | frontend sends `{session_id, reason, note, staff}`; server expects `{slip_id, reason}` |

## Decision (owner: 005-inventory)
Align on the **wizard contract** (extend server) as the sanctioned API, since the
shipped frontend already implements it. Update the four ❌ rows to ✅ in `app.py`
in the same commit as `contracts/api.md`.