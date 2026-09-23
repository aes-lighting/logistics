# Ops — Cron / Scheduled Jobs

Both scripts run from `server/` with the same `.env`.

## 1. PM reminder (day before delivery, missing ticket)
```bash
0 8 * * * cd /path/to/aes_logistics/server && /path/to/python3 send_reminders.py >> /var/log/aes_logistics/reminders.log 2>&1
```
Emails each PM for deliveries scheduled **tomorrow** with no ticket yet
(`deliveries_needing_reminder` → `mark_reminder_sent`).
Requires SMTP env.

## 2. Daily incoming-inventory report (end of day)
```bash
0 18 * * * cd /path/to/aes_logistics/server && /path/to/python3 send_daily_inventory_report.py >> /var/log/aes_logistics/daily_report.log 2>&1
```
⚠️ **BROKEN at HEAD (F5)** — `import auth` fails (module deleted in `8c92283`).
Fix per `001-WS-2`: replace `auth.list_users()` with the auth-service admin/users
call, filter to `pm`/`admin` roles. **Requires `PUBLIC_BASE_URL`** in `.env` for
clickable links.

## Notes
- Logs: create `/var/log/aes_logistics/` (or use the project-relative path of your choice).
- Both scripts need working SMTP (`SMTP_*`) or they send nothing (they log warnings, don't raise).
- The report goes to PMs + admins; broadening recipients is a one-line change in the script.