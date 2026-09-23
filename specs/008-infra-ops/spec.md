# Spec 008 — Infra & Operations

## Filesystem / deployment
- **Docker**: `Dockerfile` — `python:3.12-slim` + `tesseract-ocr`, copy
  `driver_app/ pm_portal/ server/`, gunicorn `-w 2 -b 0.0.0.0:${PORT:-5000} --timeout 120`.
  Working dir `/app/server`. README admits the image was **not built/run** by its
  author ("Docker daemon unavailable") — treat as unverified until `docker build` passes.
- **docker-compose**: ports 5000; env `server/.env`; volumes `./data/{organized,
  incoming, schedule_files}` + **legacy `auth_store.json` / `schedule_store.json`
  mounts** (auth_store inert at HEAD — F6). `restart: unless-stopped`.
- **Railway**: `railway.json` dockerfile builder.
- **Quick test / tunnel**: `start.sh` (venv, .env bootstrap, cloudflared
  trycloudflare → printed URL) + `AES_Logistics_Launcher.bat` (WSL shim).
- **Production (non-Docker)**: gunicorn 127.0.0.1:5000 behind nginx + TLS/systmd (README §4).

## Data roots
`server_config.json`: relative `./incoming`, `./organized` etc. Absolute paths
recommended for production (`/mnt/deliveries/…`).

## Security posture (full detail in `ops/security.md`)
- HTTPS required (PWA camera + install refuse plain http).
- **Secrets in git**: F1 (.env tracked) + F2 (hardcoded AES key) + broken
  `.gitignore` trailing space → **must be remediated before any public/third-party exposure**.

## Cron
- `send_reminders.py` (8am): PM reminder for next-day missing-ticket.
- `send_daily_inventory_report.py` (6pm): **BROKEN at import** (F5) until `001-WS-2`.
See `ops/cron.md` for exact crontab lines.

## Tests
Only `server/test-app.py` (import + `/api/health`). No CI. Add real tests (each
spec's tasks) and a GitHub Actions workflow when CI is acceptable.

## Tasks
- [ ] First `docker compose up -d --build` genuinely (README unverified).
- [ ] Productize data roots to absolute paths (config doc in `templates/`).
- [ ] Secrets purge (F1/F2) + `.gitignore` fix.
- [ ] Add CI (build + test) once secrets are clean.
- [ ] Verify gunicorn + nginx + certbot reference config (templates/).