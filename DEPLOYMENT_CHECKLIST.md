# AES Logistics — Deployment Checklist

Use this checklist to track your Railway.app deployment step-by-step.

## 🚀 Pre-Deployment (Before Railway Setup)

- [ ] Code is ready (this zip file)
- [ ] You have a Railway.app account (create one at https://railway.app)
- [ ] You have admin email and password ready
- [ ] You have SMTP settings (email provider) ready

---

## 📋 Railway Deployment Setup

### Account & Project
- [ ] Logged into Railway.app
- [ ] Created a new project
- [ ] Chose deployment method (GitHub or Repo upload)

### Environment Variables (Add in Railway dashboard)
- [ ] `FLASK_SECRET_KEY` — generated secret key
- [ ] `ADMIN_EMAIL` — admin@aes-energy.com (or your email)
- [ ] `ADMIN_PASSWORD` — secure password
- [ ] `SMTP_HOST` — smtp.office365.com or your provider
- [ ] `SMTP_PORT` — 587
- [ ] `SMTP_USERNAME` — your sending email
- [ ] `SMTP_PASSWORD` — email password
- [ ] `SMTP_FROM` — your sending email
- [ ] `SMTP_USE_TLS` — true
- [ ] `TWILIO_ACCOUNT_SID` — (optional for testing)
- [ ] `TWILIO_AUTH_TOKEN` — (optional for testing)
- [ ] `TWILIO_FROM_NUMBER` — (optional for testing)
- [ ] `GOOGLE_MAPS_API_KEY` — (optional for testing)

### Storage Volumes (Add in Railway Service Settings)
- [ ] Volume mounted: `/app/server/organized` (50 GB)
- [ ] Volume mounted: `/app/server/incoming` (20 GB)
- [ ] Volume mounted: `/app/server/schedule_files` (5 GB)

### Build & Deploy
- [ ] Clicked "Deploy" and build started
- [ ] Build completed successfully (check Logs)
- [ ] Service is running (green status)
- [ ] Public URL assigned (e.g., `https://aes-logistics-prod-xyz.railway.app`)

---

## ✅ Post-Deployment Testing

### Driver App
- [ ] Opened public URL in browser
- [ ] Driver PWA interface loads
- [ ] On mobile: "Add to Home Screen" prompt appears
- [ ] Can take a test photo of a ticket
- [ ] Can take a test photo of a pallet/box

### PM Portal
- [ ] Opened `{public-url}/pm`
- [ ] Logged in with admin credentials
- [ ] Dashboard loaded without errors
- [ ] Can view delivery schedule (if any exist)

### Photo Upload
- [ ] Took test photos in driver app
- [ ] Clicked "Sync Now"
- [ ] Photos uploaded successfully
- [ ] Photos appear in organized folder (via Railway volume)

### Email (SMTP)
- [ ] Sent a test email from PM portal (if that feature exists)
- [ ] Email arrived in mailbox
- [ ] No SMTP errors in logs

---

## 📱 Driver Rollout

### Installation Instructions for Drivers
- [ ] Drivers have the public URL
- [ ] On iOS: open Safari, go to URL, tap Share → Add to Home Screen
- [ ] On Android: open Chrome, go to URL, tap menu → Add to Home Screen
- [ ] App icon installed on home screen
- [ ] App opens full-screen when tapped

### First Day Testing
- [ ] Driver logs in with their name + code
- [ ] Driver takes ticket and pallet photos
- [ ] Photos appear in app (offline-capable)
- [ ] Driver taps "Sync Now" at end of shift
- [ ] Server receives photos and organizes them

---

## 🔧 Post-Launch Maintenance

### First Week
- [ ] Monitor app logs daily for errors
- [ ] Verify OCR is reading job numbers correctly
- [ ] Check if photos are organized properly
- [ ] Collect driver feedback

### Tune as Needed
- [ ] If OCR job number regex is wrong, update `server/server_config.json`
  - Redeploy (just push code; Railway auto-rebuilds)
- [ ] If SMTP settings need updating, update env vars and restart
- [ ] If volumes are full, request expansion from Railway

### Performance Checks
- [ ] Photo upload speed acceptable?
- [ ] App responsive on slow 4G networks?
- [ ] Any memory/CPU issues in Railway dashboard?

---

## 📞 Support & Escalation

If something goes wrong:

1. **Check Railway Logs** — most issues show up there
   - In Railway dashboard → service → Logs tab
   - Search for `ERROR` or `Exception`

2. **Common Fixes:**
   - Env variables missing → add them in Railway dashboard
   - Volumes full → request expansion
   - OCR not working → check `server_config.json` job number regex
   - SMTP errors → verify email credentials

3. **Get Help:**
   - Railway docs: https://docs.railway.app
   - Your deployment guide: `RAILWAY_DEPLOYMENT.md` (in this folder)

---

## ✨ Success!

Once all checkboxes are green, AES Logistics is live and drivers can start using it. 🎉

---

**Last Updated:** August 2026  
**Contact:** Chris (Informatable LLC)
