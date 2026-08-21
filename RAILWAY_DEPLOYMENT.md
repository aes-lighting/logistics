# AES Logistics — Railway.app Deployment Guide

This guide walks you through deploying AES Logistics to Railway.app, which will give you a public URL that drivers and PMs can access from their phones and desktops.

## Prerequisites

- A Railway.app account (free, https://railway.app)
- Your code uploaded (this zip file or GitHub repo)
- 10–15 minutes to complete setup

---

## Step 1: Create a Railway Account

1. Go to https://railway.app
2. Click **"Sign Up"** (or sign in if you already have an account)
3. Choose email or GitHub sign-in
4. Verify your email

---

## Step 2: Create a New Railway Project

1. In the Railway dashboard, click **"New Project"**
2. Choose **"Deploy from GitHub"** (recommended for updates) OR **"Deploy from Repo"** (if you just have this code as a zip)
3. If deploying from GitHub:
   - Link your GitHub account
   - Select the repository containing your code
   - Railway will auto-detect it's a Docker project
4. If deploying from Repo:
   - Upload this folder; Railway will detect the Dockerfile

---

## Step 3: Configure Environment Variables

Railway will now show a deployment screen. Before it builds, **add your environment variables**:

### Click "Add Variable" and fill in each of these:

```
FLASK_SECRET_KEY=<generate-a-secret-key>
ADMIN_EMAIL=admin@aes-energy.com
ADMIN_PASSWORD=<choose-a-password>

SMTP_HOST=smtp.office365.com (or your mail provider)
SMTP_PORT=587
SMTP_USERNAME=your-sending-account@aes-energy.com
SMTP_PASSWORD=your-password-or-app-password
SMTP_FROM=your-sending-account@aes-energy.com
SMTP_USE_TLS=true

TWILIO_ACCOUNT_SID=<your-twilio-sid> (optional for testing)
TWILIO_AUTH_TOKEN=<your-twilio-token>
TWILIO_FROM_NUMBER=+15551234567

GOOGLE_MAPS_API_KEY=<your-google-maps-key>
```

**Generate a Flask secret key:**
```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```

> **Note:** Don't have Twilio or Google Maps yet? Leave those blank for now; you can add them later. They're optional.

---

## Step 4: Configure Storage Volumes

Your app needs persistent storage for uploaded photos and organized delivery folders. Railway uses **"Volumes"** for this.

1. In the Railway project dashboard, find your deployed service
2. Click **"Settings"** tab → **"Volumes"**
3. Add these mount points:

| Mount Path | Size |
|---|---|
| `/app/server/organized` | 50 GB |
| `/app/server/incoming` | 20 GB |
| `/app/server/schedule_files` | 5 GB |

These directories will persist even when you redeploy the app.

---

## Step 5: Deploy

1. Click the **"Deploy"** button
2. Railway will:
   - Build the Docker image (~2–3 minutes)
   - Start the container
   - Assign you a public URL (e.g., `https://aes-logistics-prod-abc.railway.app`)

Check the **"Logs"** tab to watch the build. It should end with something like:
```
[2026-08-21 13:45:00] Listening on 0.0.0.0:5000
```

---

## Step 6: Test Your Deployment

Once the build completes, Railway shows your **public URL** in the service overview.

1. **Test the driver app:**
   - Open the URL in your browser (or phone): `https://your-railway-url.railway.app`
   - You should see the driver PWA "Add to Home Screen" prompt on mobile
   - On desktop, you'll see the driver app interface

2. **Test the PM portal:**
   - Go to `https://your-railway-url.railway.app/pm`
   - Log in with your admin credentials (the email and password from env vars)

3. **Test admin panel:**
   - Go to `https://your-railway-url.railway.app/admin` (if it exists)
   - Verify you can manage drivers, view uploads, etc.

---

## Step 7: Drivers Install the App

Now your drivers can use it. They visit your public URL on their phone and:

1. Open Safari (iOS) or Chrome (Android)
2. Go to `https://your-railway-url.railway.app`
3. Tap the **Share** button
4. Tap **"Add to Home Screen"**
5. Tap **"Add"**

The app icon now sits on their home screen like any other app. When they tap it, it opens full-screen and works offline for photo capture.

---

## Step 8: Custom Domain (Optional)

By default, Railway gives you a `*.railway.app` URL. If you want a custom domain like `logistics.aes-energy.com`:

1. In Railway dashboard → service settings → **"Domains"**
2. Click **"Add Custom Domain"**
3. Enter `logistics.aes-energy.com`
4. Railway shows DNS records to update in your domain registrar
5. Update your DNS, wait ~5 minutes for propagation

---

## Troubleshooting

**"Build failed" or "Deployment error":**
- Check **Logs** tab for the exact error
- Common issues:
  - Missing `requirements.txt` in server/ (it's there)
  - Python/tesseract version mismatch (unlikely with pre-built image)
  - Environment variables not set (double-check step 3)

**"App crashes after deploy":**
- Check Logs for Flask errors
- Verify `FLASK_SECRET_KEY` and `ADMIN_PASSWORD` are set
- Make sure volumes are mounted (step 4)

**"Photos won't upload":**
- Confirm volume at `/app/server/organized` is mounted
- Check app logs for permission errors
- Verify OCR is working (in logs, you'll see tesseract output)

**"OCR not reading job numbers":**
- The regex in `server_config.json` is a placeholder
- Test it against real packing slip photos
- If it's wrong, update the pattern and redeploy (Railway auto-rebuilds)

---

## Updating Your Code

If you push updates to GitHub:
1. Railway auto-detects the change and rebuilds
2. Your public URL stays the same
3. Sessions persist (unless you change `FLASK_SECRET_KEY`)

If you're not using GitHub:
1. Re-upload the code
2. Railway rebuilds automatically

---

## Production Checklist

Before handing this to the full AES team:

- [ ] Test driver app on an actual phone (iOS and Android)
- [ ] Test PM portal in desktop Chrome and Safari
- [ ] Verify photos upload and are organized by job number
- [ ] Confirm SMTP settings work (test email sending)
- [ ] Set a proper admin password (not placeholder)
- [ ] Test OCR against real packing slips; update regex if needed
- [ ] Brief drivers on how to install the app
- [ ] Monitor logs for first week of live usage
- [ ] Set up backup/export of photos (ask Railway about backup options)

---

## Need Help?

- **Railway docs:** https://docs.railway.app
- **Docker issues:** Check Logs in Railway dashboard
- **App logic bugs:** Review `server/app.py` and open a support ticket

Good luck! Your AES Logistics app is now live on the internet. 🚀
