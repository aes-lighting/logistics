# Spec 003 — PM Portal (`/pm`)

## Purpose
Desk/laptop UI for PMs + admins: calendar sync, scheduling, ticket
upload/generate/revise, send-to-PM, admin tools (user register/delete), and the
inventory tab with Excel export.

## Files
`pm_portal/{index.html, app.js, styles.css}` (served at `/pm`).

## Behavior (from `app.js`)
- **Auth**: `api()` helper attaches `Authorization: Bearer <email>` (from
  localStorage `aes_cached_user`) to every call. Login via `/api/auth/login`;
  only role `pm`/`admin` admitted; dashboard otherwise.
- **Calendar**: `GET/POST /api/schedule/calendar/settings` (ICS URL); upcoming
  events list with `already_scheduled` (client derives); Set Up Delivery prefills.
- **Create delivery**: POST `/api/schedule` with all fields + optional
  customer/PO/job/method + `calendar_event_uid`; resets form; refreshes lists.
- **Deliveries table**: GET `/api/schedule`; actions — Upload Ticket (`/ticket`),
  Generate/Revise (`/generate_ticket` / `/revise_ticket` with `line_items`),
  View (modal: line-item checkmarks, signatures, photos, geotag), Send to PM
  (`/send_copy_to_pm`), Delete (`DELETE /api/schedule/<id>`).
- **Inventory tab**: GET `/api/inventory`, Mark Shipped
  (`/api/inventory/<id>/remove`), Export (`window.open('/api/inventory/export')`).
- **Admin Tools**: register (`/api/auth/admin/register_user`), list
  (`/api/auth/admin/users`), delete (`/api/auth/admin/users/<int>`).

## Contracts
Consumes `001-server/contracts/api.md`. Note frontend admin **delete button** uses
`data-user-id` → `users/<user_id>`; register expects `{name,email,role}`.

## Open questions
- Role gate for PM is client-side (`result.role`) + server `@pm_or_admin_required`
  stub (F3). Admin tools claim pm/admin; confirm server actually restricts.
- Driver dropdown `/api/schedule/drivers` returns `[{name}]`; scheduling stores
  `assigned_driver` as name — a driver whose display name differs from the
  registered name breaks assignment matching. Flag for review.
- `already_scheduled` is computed client-side from the changed UID set — confirm
  the server change of `linked_event_uids` feeds the response (server returns
  just events; client dedups against deliveries).