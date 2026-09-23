# Ops — Runbook

## Prereqs
- Python 3.9+; Tesseract OCR (`sudo apt-get install tesseract-ocr` on Ubuntu/Debian).
- `pip install -r server/requirements.txt`.

## Quick local test (no real use)
```bash
cd server && python3 app.py            # serves :5000
```

## Docker (portable; uses ./data for persistence)
```bash
cp server/.env.example server/.env     # then fill in
mkdir -p data/organized data/incoming data/schedule_files
touch data/auth_store.json data/schedule_store.json   # auth_store is legacy/inert (F6)
docker compose up -d --build
curl http://localhost:5000/api/health
docker compose logs -f
docker compose down
```
> ⚠️ Image was never actually built by the author — treat the first `--build`
> as a real test. If it fails, post the error; fix per `008-infra-ops`.

## One-click launcher (WSL)
Double-click `AES_Logistics_Launcher.bat` → `start.sh` provisions venv + .env +
cloudflared tunnel, prints `https://….trycloudflare.com` (+ `/pm` for portal).
Keep the window open; new URL each run.

## Production (non-Docker)
```bash
cd server && gunicorn -w 2 -b 127.0.0.1:5000 app:app
```
Reverse proxy (nginx) with TLS (certbot); systemd unit (references in README §4).

## Smoke test
```bash
python3 server/test-app.py        # imports all server modules + hits /api/health
```

## Known-broken to avoid surprising yourself
- `send_daily_inventory_report.py` **crashes at import** (F5, no `auth` module).
- Incoming-Inventory wizard + Ready-to-Pack + Send-to-PM frontend flows hit
  **missing server endpoints** at HEAD (F4) — they will 404 until `005-inventory`
  work lands.
- `.env` is still git-tracked (F1); do not publish the repo until `ops/security.md`
  is actioned.