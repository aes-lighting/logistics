# Railway Deployment — Quick Start (5 Minutes)

**TL;DR:** Get AES Logistics live in 5 minutes. Full details in `RAILWAY_DEPLOYMENT.md`.

## 1. Create Railway Account
https://railway.app → Sign up (free)

## 2. Create New Project
Dashboard → New Project → Deploy from Repo (upload this folder)

## 3. Add Environment Variables
In the deployment screen, click "Add Variable" and add these (minimum):

```
FLASK_SECRET_KEY=<run: python3 -c "import secrets; print(secrets.token_hex(32))">
ADMIN_EMAIL=admin@aes-energy.com
ADMIN_PASSWORD=YourChosenPassword123

SMTP_HOST=smtp.office365.com
SMTP_PORT=587
SMTP_USERNAME=your-email@company.com
SMTP_PASSWORD=your-password
SMTP_FROM=your-email@company.com
SMTP_USE_TLS=true
```

**Don't have Twilio/Google Maps yet?** Leave them blank for now.

## 4. Add Storage Volumes
Service Settings → Volumes → Add these:
- `/app/server/organized` → 50 GB
- `/app/server/incoming` → 20 GB

## 5. Deploy
Click **Deploy** button. Wait 2–3 minutes for build.

## 6. Test
Once done, Railway gives you a public URL like:
```
https://aes-logistics-prod-abc123.railway.app
```

- Visit it in your browser → see driver app
- Visit `/pm` → log in with admin email/password

## 7. Drivers Use It
They visit your URL on their phone and:
1. Tap Share → "Add to Home Screen"
2. Open the app icon
3. Log in with their name + a code (you create codes in admin panel)

---

## Done! ✅

Your AES Logistics warehouse app is now live on the internet.

Drivers can install it on their phones. PMs can access `/pm` from desktop.

For detailed deployment info or troubleshooting, see **RAILWAY_DEPLOYMENT.md**.
