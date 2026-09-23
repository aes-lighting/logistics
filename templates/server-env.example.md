# ── AES Logistics · server/.env.example (reference copy for spec kit) ──
# Copy to ".env" (same folder) and fill in real values. NEVER commit the real ".env".

# SMTP (outgoing email: flags, tickets, reports, completion)
SMTP_HOST=smtp.office365.com
SMTP_PORT=587
SMTP_USERNAME=your-sending-account@aes-energy.com
SMTP_PASSWORD=your-password-or-app-password
SMTP_FROM=your-sending-account@aes-energy.com
SMTP_USE_TLS=true

# Session-cookie signing key — generate: python3 -c "import secrets; print(secrets.token_hex(32))"
FLASK_SECRET_KEY=replace-with-a-long-random-string

# Bootstrap admin (first-run auto-registration in embedded-auth era — verify with auth-service flow)
ADMIN_EMAIL=admin@aes-energy.com
SHARED_PASSWORD=aes

# Twilio SMS ("driver on the way")
TWILIO_ACCOUNT_SID=replace-with-your-twilio-account-sid
TWILIO_AUTH_TOKEN=replace-with-your-twilio-auth-token
TWILIO_FROM_NUMBER=+155****4567

# Google Maps Distance Matrix (ETA) — billing-enabled project
GOOGLE_MAPS_API_KEY=replace-with-your-google-maps-api-key

# Public URL for clickable links in emails (domain or tunnel URL)
PUBLIC_BASE_URL=https://your-domain-or-tunnel-url

# ── AES File Service mirror (app.py) ──
# ⚠️ app.py:93 still HARDCODES a real fallback key (F2) — set these and remove the default.
AES_API_URL=http://71.172.107.128:3001
AES_API_KEY=replace-with-your-key

# ── auth-service microservice ──
AUTH_SERVICE_URL=https://auth-service-production-bb0d.up.railway.app