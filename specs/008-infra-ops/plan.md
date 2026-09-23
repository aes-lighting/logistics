# Spec 008 — Infra & Ops: Plan & Tasks

## Plan
1. **Bootstrap & verify** the Docker path for real (it is currently unbuilt).
2. **Purge secrets** before anything else that touches wider distribution (F1/F2).
3. Build a CI workflow: build image + run `test-app.py`.
4. Codify production run (gunicorn/nginx certbot) as templates.

## Tasks
- [ ] Run `docker compose up -d --build`; fix any path/OCR issues found; note transcript.
- [ ] `.gitignore` fix (trailing space) + `git rm --cached .env`; rotate hardcoded key (F2).
- [ ] Absolutize data roots in config; document in templates.
- [ ] Add GitHub Actions: build + `test-app.py`.
- [ ] gunicorn/nginx/certbot systemd template (ops).