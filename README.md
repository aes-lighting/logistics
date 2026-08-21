# AES Logistics — Delivery Photo App

A small system with two parts:

1. **Driver app** (`driver_app/`) — a Progressive Web App (PWA) drivers install
   to their phone home screen. They take a ticket photo and a pallet/box photo
   for each delivery; the app won't let them mark a delivery "complete" until
   both are present. At end of shift, they tap **Sync Now**.
2. **Server** (`server/`) — receives synced deliveries, reads the job number
   off the ticket via OCR, and files every photo into `organized/Job_<number>/`
   on your server automatically.

This replaces the earlier folder-watching scripts: because the app tags each
photo's type and groups them by delivery *at the moment it's taken*, the
server no longer has to guess which photos belong together or which one is
the ticket — it only has to read the job number.

---

## 1. Why this isn't an App Store app

This is a **installable web app**, not a native iOS/Android app submitted to
an app store. That's a deliberate choice, not a shortcut:

- No Apple Developer account ($99/year), no Mac, no code signing needed.
- No app store review process or approval wait.
- Drivers install it in about 15 seconds by visiting a URL and tapping
  "Add to Home Screen" — after that it looks and behaves like any other app
  icon, opens full-screen, and works offline for capturing photos.
- If you later decide you want a true native app (e.g. for deeper OS
  integration), this same server/API can stay as-is — only the driver-facing
  app would need to be rebuilt natively.

## 2. Requirements on your server

```bash
# Ubuntu/Debian
sudo apt-get install tesseract-ocr

# Python packages
pip install -r server/requirements.txt --break-system-packages
```

You need Python 3.9+ and Tesseract OCR installed (used to read the job number
off ticket photos).

## 3. Configure

Edit `server/server_config.json`:

```json
{
  "job_number_pattern": "job\\s*#?\\s*:?\\s*(?P<job>\\d{3,8})",
  "incoming_dir": "./incoming",
  "dest_dir": "./organized",
  "review_folder": "needs_review_no_job_number",
  "incomplete_flag_filename": "INCOMPLETE_missing_pallet_photo.txt"
}
```

**`job_number_pattern` is a placeholder.** It needs to match how job numbers
actually appear on your real packing slips (e.g. `Job #12345` vs
`JO-2024-0087` vs a handwritten number with no label). Send me a couple of
real photos and I'll tune this — right now it's my best guess, not tested
against your actual documents.

Set `incoming_dir` / `dest_dir` to real absolute paths on your server (e.g.
`/mnt/deliveries/incoming`, `/mnt/deliveries/organized`) once you're past
local testing.

## 4. Run it

**Docker (recommended if you want a clean, portable setup):** see section 4a
below — this avoids Python version issues, Tesseract PATH problems, and
"which folder am I in" confusion entirely.

**Quick test (not for real use):**
```bash
cd server
python3 app.py
```

**Production (recommended if not using Docker):** run behind gunicorn + a
reverse proxy with HTTPS. HTTPS is required — phones will refuse camera
access and PWA install on a plain `http://` site (except `localhost`).

```bash
cd server
gunicorn -w 2 -b 127.0.0.1:5000 app:app
```

Then put nginx (or your existing reverse proxy) in front of it with a TLS
certificate (e.g. via Let's Encrypt / certbot), forwarding your public domain
to `127.0.0.1:5000`. A systemd unit to keep gunicorn running:

```ini
# /etc/systemd/system/aes-logistics.service
[Unit]
Description=AES Logistics server
After=network.target

[Service]
WorkingDirectory=/path/to/aes_logistics/server
ExecStart=/usr/bin/gunicorn -w 2 -b 127.0.0.1:5000 app:app
Restart=always
User=your_service_user

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable --now aes-logistics
```

## 4a. Running with Docker instead

This packages the whole app (driver PWA + PM portal + Flask API + Tesseract)
into one image, so there's no "which Python version," "where's Tesseract,"
or "which folder am I in" ambiguity — it either builds or it doesn't.

**One-time setup:**
```bash
cp server/.env.example server/.env
nano server/.env   # fill in FLASK_SECRET_KEY, ADMIN_EMAIL, ADMIN_PASSWORD, etc.

mkdir -p data/organized data/incoming data/schedule_files
touch data/auth_store.json data/schedule_store.json
```

That `data/` folder is what makes updates safe: it lives on your host
machine, outside the image, so rebuilding with new code never touches
driver accounts, delivery records, uploaded tickets, or photos.

**Build and run:**
```bash
docker compose up -d --build
```

**Check it's alive:**
```bash
curl http://localhost:5000/api/health
```

**View logs:**
```bash
docker compose logs -f
```

**Updating to new code later** (this is the whole point of doing it this way):
```bash
# get the new code (unzip a fresh aes_logistics.zip over this folder,
# or `git pull` if you're using git — either way, leave data/ alone)
docker compose up -d --build
```
Your `data/` folder is untouched; only the app code rebuilds.

**Stopping it:**
```bash
docker compose down
```

You'll still need something in front of this for HTTPS (see section 5) —
Docker packages the app itself, but doesn't solve the HTTPS requirement.
ngrok works exactly the same way against a Dockerized server as a
non-Dockerized one — just point it at port 5000 either way.

**A note on what I could and couldn't verify:** I don't have a Docker daemon
available in my own environment, so I wasn't able to literally build and run
this image myself. I did carefully verify every path reference (the
Dockerfile's copy paths, the app's static-file directory resolution, and the
relative paths in `server_config.json`) all line up correctly for this
container layout — but running `docker compose up -d --build` for the first
time is genuinely the first real test of it. If it fails, send me the error
output and I'll fix it.

## 4b. One-click launcher (easiest way to test)

Included in this zip: `start.sh` and `AES_Logistics_Launcher.bat`. Together
they handle everything — Python setup, dependencies, `.env` creation, server
startup, and a public HTTPS link — so testing is just "double-click and
read the URL," no typing commands each time.

**One-time setup:**
1. Unzip this project into your WSL home folder, e.g. `~/aes_logistics_latest`
   (if you use a different folder name, edit that path inside
   `AES_Logistics_Launcher.bat` in Notepad first).
2. Copy `AES_Logistics_Launcher.bat` to your Windows Desktop (or anywhere
   convenient) — it can live outside the project folder.

**Every time you want to test:**
1. Double-click `AES_Logistics_Launcher.bat`.
2. A window opens and does its thing. **First run only**, it'll stop partway
   and tell you to edit `server/.env` with your admin email/password — do
   that, save, and double-click the launcher again.
3. Once running, look for a line like:
   ```
   https://random-words-here.trycloudflare.com
   ```
   That's your link — open it on your phone, or send it to anyone else
   testing. Add `/pm` to the end for the Project Management portal.
4. **Keep the window open** while testing — closing it stops the server.
   Closing and reopening later gives you a **new** URL each time (the free
   tunnel doesn't keep the same address between runs).

This uses [Cloudflare Tunnel](https://github.com/cloudflare/cloudflared) —
no account or signup needed, `start.sh` downloads it automatically the
first time it runs.

## 5. Get it onto driver phones

1. Once the server is live at your HTTPS domain (e.g. `https://delivery.yourcompany.com`),
   send that link to each driver.
2. **iPhone:** open the link in Safari → Share icon → "Add to Home Screen".
   **Android:** open the link in Chrome → menu (⋮) → "Add to Home screen" / "Install app".
3. On first open, the app asks the driver's name once — it's remembered on
   that phone from then on.

No app store, no install file, no IT push needed for a small fleet.

## 6. How a driver / warehouse worker uses it

1. Open the app, log in.
2. **Choose a role from the menu that appears — always exactly three tiles:**
   - **Driver** — delivery photos and tickets (the ad-hoc "New Delivery" flow,
     and "My Deliveries" for anything scheduled and packed).
   - **Warehouse** — Incoming Inventory (packing slips coming in) and
     Outgoing Inventory (packing/checking off/signing tickets going out).
   - **Project Management** — opens the PM Portal (`/pm`).
   - **Driver-type accounts** see Driver + Warehouse —
     the same person can do either job, switching anytime via the ⟲ icon on
     the home screen without logging out.
   - **PM and admin accounts** see all three tiles, since PM is meant to
     have access to everything — including being able to step into Driver
     or Warehouse mode directly if needed.
3. Picking a tile filters the home screen to just that section — e.g.
   Driver mode hides all Warehouse content, and vice versa.
4. **In Driver mode:** tap **+ New Delivery** for an ad-hoc delivery (ticket
   photo + pallet photo + complete), or open something under **My
   Deliveries** if a PM has scheduled and Warehouse has already packed it —
   see section 9 for that full flow.
5. **In Warehouse mode:** use **+ Incoming Inventory** for packing slips
   arriving, or **Outgoing Inventory — Ready to Pack** for orders a PM has
   ticketed that need to be packed, checked off, and signed before a driver
   can take them (see section 9).
6. For the ad-hoc Driver flow: **Complete Delivery** only becomes available
   once at least a ticket photo and a pallet photo have been taken. Photos
   are stored on the phone — no signal needed until Sync Now at end of
   shift.

## 7. What happens on the server automatically

For each synced ad-hoc delivery:
- OCR reads the ticket photo(s) for a job number.
- **Job number found** → all of that delivery's photos move to
  `organized/Job_<number>/`.
- **No pallet/box photo in the delivery** (shouldn't normally happen since the
  app requires it, but covers edge cases like a partial upload) → an
  `INCOMPLETE_missing_pallet_photo.txt` file is dropped in that job's folder
  so office staff notice at a glance.
- **No job number could be read** → the whole delivery goes to
  `organized/needs_review_no_job_number/<delivery_id>/` instead of guessing
  wrong.
- GPS/location data already in a photo's EXIF is preserved automatically —
  files are only ever moved, never re-encoded.

## 8. Login

One unified login for everyone — an `@aes-energy.com` email and a single
shared password. No more separate driver PINs, no more separate admin/PM
login screens. The same login form works on the driver app and the PM
Portal, and works identically for a driver, a warehouse worker, a project
manager, or an admin — what's different is only which **role** is attached
to that email, which decides what shows up after logging in.

**⚠️ Security note, worth actually reading:** every account shares the
*same* password. That means anyone who knows it can log in as anyone
else — including as an admin. This is a deliberate simplification to make
testing painless, not something to carry into real production use without
tightening (per-user passwords, or a real SSO provider, before this
matters for real). I implemented exactly what was asked and hashed it at
rest regardless, but wanted that trade-off stated plainly rather than
quietly built in.

### Setting it up

```bash
cd server
cp .env.example .env
# then edit .env and set:
#   ADMIN_EMAIL=admin@aes-energy.com     (or whichever email should start as admin)
#   SHARED_PASSWORD=aes                   (or whatever you want everyone to use)
```

On first startup, that `ADMIN_EMAIL` is automatically registered with the
admin role — that's your way in to start registering everyone else. Nobody
else can self-register anymore; every account (driver, warehouse, PM,
admin) has to be added first via Admin Tools.

**Changing the shared password later** is just: edit `SHARED_PASSWORD` in
`.env`, restart the server — it takes effect for every account at once.

### Registering everyone

**PM Portal (`/pm`) → Admin Tools tab** — available to both PM and admin
logins:
- **Register a User** — name, `@aes-energy.com` email, and a role (Driver /
  Warehouse, Project Manager, or Admin). They can log in immediately with
  that email and the shared password.
- A live table of everyone currently registered.

### Staying logged in

Once logged in, a session is remembered for 30 days (a signed cookie, not
stored in plaintext) so people don't need to log in every single delivery.
If the phone is offline when the app is opened, it'll use the last known
login rather than force a login it can't verify — but the *first* login on
a given phone always requires being online.

## 9. Scheduled Delivery (calendar-linked ticket, checkoff, signature)

A separate, third flow — alongside the ad-hoc "New Delivery" flow and
Incoming Inventory — for deliveries that are scheduled in advance. This is
the one that ties into your calendar, a new PM portal, and produces a
signed, emailed delivery record.

### The pieces

- **PM Portal** — a new page at `/pm` (e.g. `https://yourdomain.com/pm`),
  separate from the driver app, meant for a desk/laptop rather than a phone.
  PMs log in here to connect your calendar, schedule deliveries, and get a
  ticket ready — either by uploading a photo/PDF or by using the built-in
  **Delivery Ticket Generator**, which renders a ticket matching AES
  Lighting Group's actual paper Delivery Receipt form (company header,
  DELIVERED TO / DATE / CUSTOMER / CUSTOMER PO# / JOB NAME / AES JOB NUMBER
  / DELIVERY METHOD fields, and a line-items table with TYPE, QTY, BOXES,
  MODEL #, DESCRIPTION, MFG columns).
- **Calendar sync (read-only)** — the PM pastes an ICS feed URL from Outlook
  or Google Calendar. This is one-way: the portal reads upcoming events to
  surface them as "set this up as a delivery" prompts. Nothing is written
  back to your calendar. See below for how to get that URL from either
  platform.
- **Two checkbox stages, matching the paper form's LOADED / DELIVERED /
  RECEIVED columns:**
  - **LOADED (Outgoing Inventory / Warehouse)** — once a ticket exists
    (uploaded or generated), it has to be **packed and signed off by
    warehouse** before any driver can see it. Whoever packs the order
    checks off each line item (or a single overall confirmation if the
    ticket was just an uploaded photo with nothing structured to check) and
    signs — their signature, separate from the receiver's later.
  - **DELIVERED (driver, on site)** — when the ticket has line items, the
    driver checks off **each item individually** as it's unloaded from the
    truck, instead of one blanket "everything's fine" box. Every item has
    to be checked before the delivery can be completed.
  - *(RECEIVED, the third column on the paper form, isn't wired to a
    checkbox yet — the receiver's overall signature covers that today. Say
    the word if you want per-item receiver checkoff too.)*
- **Driver app — "My Deliveries"** — only shows deliveries that have cleared
  the packing (LOADED) step. Tapping one shows the ticket, the checkoff
  (per-item or overall, depending on the ticket), a requirement for 2+
  material photos, and a signature pad for the receiver.

### Ready to Pack: Revise and Send to PM

The Warehouse "Ready to Pack" list (where the LOADED packing step happens)
now shows **three buttons per delivery** instead of one tap:

- **Revise Ticket** — edit the line items and regenerate the ticket, right
  from the phone (or, for header fields like Customer/PO/Job Name too, from
  the PM Portal). **Revising is always allowed, at any stage — there's no
  hard block.** Instead, the system reacts sensibly to how far along the
  delivery already is:
  - **Before packing** — just updates the ticket, nothing else to reconcile.
  - **Already packed, driver hasn't started** — since the old checked-off
    items no longer match the revised ticket, it's automatically **reset
    back to "needs packing"** and reappears in Ready to Pack for a fresh
    checkoff and signature. Nothing is lost — the previous pack info is
    simply cleared so it can't be mistaken for still being valid.
  - **Driver already en route, or delivery already completed** — the
    delivery's status is left alone (a driver mid-route isn't yanked back,
    and a completed delivery isn't un-completed), but the ticket record
    still updates — this is treated as a correction that the people
    involved need to coordinate on directly.
  - **Every single revision, at every stage, automatically emails both the
    assigned PM and a warehouse alert address** with the updated ticket
    attached, flagging what changed, who changed it, and — when relevant —
    that it needs to be re-packed or that the driver/receiver should be
    given a heads-up.
- **Send to PM** — a dropdown of every registered PM, to send a copy of the
  current ticket to anyone, independent of who's actually assigned to that
  job. Also available in the PM Portal.
- **Pack / Check Inventory** — the existing checkoff + signature flow,
  unchanged.

The warehouse alert address defaults to `Warehouse@aes-energy.com` —
change `warehouse_alert_email` in `server_config.json` if that's not the
right address.

### How it flows end-to-end

1. **PM connects the calendar** in the portal (paste the ICS URL, save).
2. **Upcoming events show up** in the portal. A calendar event only tells us
   there's *something* on a given date — it doesn't carry a job number or
   receiver info in a structured way, so the PM clicks **Set Up Delivery**
   on an event and fills in: job number, receiver name/email/phone, PM
   email, site address, assigned driver, and (optionally) customer name,
   customer PO#, job name, and delivery method — these last four match
   fields on the real paper form and are blank if not needed. This creates
   the actual delivery record.
3. **The day before the delivery date**, if no ticket exists yet, a reminder
   email goes automatically to the PM (see the cron setup below).
4. **The PM gets a ticket ready**, either:
   - **Upload Ticket** — a photo/PDF of an existing paper ticket, or
   - **Generate Ticket** — adds line items (each with description, quantity,
     and optionally type / model # / MFG / box count) and the app renders a
     ticket image matching the real Delivery Receipt layout.
   Both produce the same kind of artifact — everything downstream treats an
   uploaded and a generated ticket identically.
5. **Warehouse packs and checks off LOADED** (Outgoing Inventory, in
   Warehouse mode on the phone app): opens the ticket from "Ready to Pack,"
   checks off every line item (or the single overall box if there were no
   structured items), enters their name, and signs. **All items must be
   checked before this can be confirmed** — a partially-packed order can't
   be marked done. Only after this does the delivery become visible to a
   driver.
6. **On delivery day**, the assigned driver opens the app in Driver mode,
   finds it under **My Deliveries**, and taps **I'm Heading There Now** (see
   section 12 for the SMS/ETA that triggers) — then, on arrival: sees the
   ticket image and checks off each item individually as it's unloaded from
   the truck (**DELIVERED**) — or a single overall box if the ticket had no
   structured line items — takes 2+ photos of the material before it leaves
   the truck, and hands the phone to the receiver to sign. The app also
   captures the phone's live GPS location at that moment — if permission is
   denied, it still completes without it rather than blocking the delivery.
7. **On submit**, the signed ticket, the photos, and the receiver's
   signature are emailed automatically to **both the PM and the receiver**,
   along with the location and timestamp.
8. The PM can see the full record — ticket, line items with checkmarks,
   packer's signature, receiver's signature, photos, location — in the
   portal's deliveries table afterward.

### Getting an ICS feed URL

**Google Calendar:** Calendar settings → the specific calendar → "Integrate
calendar" → copy the **Secret address in iCal format**.

**Outlook / Microsoft 365:** Calendar → Share → Publish a calendar → copy
the **ICS** link (not the HTML one).

Either URL goes into the "Calendar Sync" box in the PM portal.

### Setting up PM accounts

Admin Tools now has a **Register a Project Manager** form (alongside driver
registration) — enter their name, email, and an initial password, and
they can immediately log into the PM Portal at `/pm` with those credentials.

### Setting up the daily reminder

The reminder that emails a PM the day before a delivery if no ticket has
been uploaded yet is a separate script, meant for cron:

```bash
# crontab -e
0 8 * * * cd /path/to/aes_logistics/server && /path/to/python3 send_reminders.py >> /var/log/aes_logistics/reminders.log 2>&1
```

It uses the same `.env` SMTP settings as the flag-email feature — nothing
extra to configure if that's already set up.

### What I tested vs. what still needs a real-world check

I tested, end-to-end against the running server: ICS parsing (with a
synthetic calendar feed, since I can't reach your real Outlook/Google
calendar from here), PM login and calendar settings, creating a scheduled
delivery, **generating a ticket from a line-item form** (verified the
rendered image looks right), **uploading** a ticket as an alternative,
confirming a driver **cannot** see a delivery before Warehouse packs it,
**rejecting a partial packing checkoff** (not all items checked), packing
succeeding once everything is checked off and signed, the driver then
seeing it, completing it with a checkbox + 2 photos + signature + geotag
(rejecting completion with fewer than 2 photos), and confirming the
resulting email is correctly addressed to **both** the PM and the receiver.
I also ran full simulated-browser tests of: the driver-side ticket screen,
the Outgoing Inventory packing screen (line-item checkboxes, the Complete
button correctly staying disabled until every item is checked + name +
signature are all present), and the PM portal (login, calendar events list,
Generate Ticket modal, Admin Tools tab, deliveries table).

What I have **not** been able to test, and what you should verify during
your pilot:
- **A real ICS feed from your actual Outlook or Google Calendar** — I only
  tested against a synthetic one I generated myself. Calendar export
  formats have small quirks between providers; confirm your real feed
  parses correctly once connected.
- **Real GPS capture on a phone** — the geolocation code is standard browser
  API usage, but I have no physical device to confirm the permission prompt
  and accuracy behave as expected on iOS vs Android.
- **Signature drawing on an actual touchscreen** — tested via simulated
  pointer events, not a finger on real glass (both the receiver's and the
  packer's signature pads use the same drawing code).

## 10. Incoming Inventory (packing slips)

A full multi-step flow for checking in incoming shipments — separate from
deliveries, and separate from Outgoing Inventory (the packing/checkoff step
covered in section 9). **This entire flow requires being online throughout**
— there's no offline queue for it, since each step (scanning, confirming,
emailing the PM, logging pallets) talks to the server immediately.

Flow on the phone (Warehouse mode → **+ Incoming Inventory**):

1. **Scan the packing slip.** Take a photo of each page — multi-page slips
   are supported, just tap **Take Photo of Next Page** for each one. Tap
   **Done Scanning — Continue** once all pages are captured.
2. **Confirm Job Number and PO Number.** Both are pre-filled from OCR if it
   found them, editable either way.
3. **PM lookup.** The first time a job number is seen, you're asked to pick
   which Project Manager owns it from a dropdown. After that, the system
   remembers the job → PM pairing automatically — no picking required for
   that job again.
4. **The PM is emailed automatically** the moment the job is confirmed, with
   all the slip's page photos attached.
5. **Pallet count.** Enter how many pallets arrived, then take one photo of
   each pallet in turn — the app tracks progress ("2 of 3 photographed") and
   won't let you continue until every pallet has a photo.
6. **Choose location(s).** Warehouse, Back Tent, Front Tent, Trailer 6,
   Trailer 4, Redbox, Front Red, CS 1036, CS 1071, CS 1058, CS 1015, Office,
   or Truck. Defaults to one location holding all the pallets — tap **+
   Split Across Another Location** to divide them (e.g. 2 pallets to Back
   Tent, 1 to Warehouse). **The location counts must add up to the pallet
   count** — the app blocks finishing until they match exactly.
7. **Comment** (optional) — anything worth noting about the shipment.
8. **Finish & Generate QR Code** — logs everything to the running inventory
   and produces a printable QR-coded PDF (see below). If no job number could
   be identified at all, **Flag** is available instead (from the confirm
   screen) — same as before: emails `PMteam@aes-energy.com` with whatever
   photos exist and a reason, rather than guessing wrong.

### The QR code / printed label

Each finished check-in gets a one-page PDF: a QR code plus the job number,
PO number, pallet count, and location(s) printed in plain text underneath
— readable at a glance even without scanning it. The QR code itself encodes
a link back to that entry in the app.

**No printer is wired up yet** (none has been purchased). The "Print QR
Code" button on the done screen opens this PDF, and your device's own print
dialog handles sending it to whatever printer is set up — this works with
any printer without server-side configuration. Once a specific printer is
purchased, tell me the make/model and direct network printing (skipping
the browser dialog entirely) is a reasonable next step.

### Running inventory report (Excel)

Every finished check-in is logged — job number, PO number, pallet count,
location(s), PM, who confirmed it, when, and any comment — building a live
record of what's been received and where it physically is.

**PM Portal → Inventory tab** shows this as a live table, and an
**Export to Excel** button downloads a `.xlsx` report with two sheets:
- **Current Inventory** — every item with full detail, ready to open,
  filter, or print.
- **Summary by Location** — pallet counts at each of the thirteen
  locations, plus a total.

This is a snapshot at the moment of export, not a live-linked spreadsheet —
re-export anytime for a fresh copy. Available to PM and admin logins; any
logged-in role can view the table itself, but the export button is
PM/admin-only.

### End-of-day report

A separate script, `send_daily_inventory_report.py`, meant for a daily cron
job (e.g. 6pm):

```bash
# crontab -e
0 18 * * * cd /path/to/aes_logistics/server && /path/to/python3 send_daily_inventory_report.py >> /var/log/aes_logistics/daily_report.log 2>&1
```

Emails every registered PM and admin a summary of everything checked in
that day — job/PO numbers, pallet counts, locations, comments, and a
clickable link to each entry (opens the app; requires being logged in,
same as any internal link). If "everyone" should mean a broader audience
than PMs + admins, that's a one-line change in the script.

It needs `PUBLIC_BASE_URL` set in `.env` (your real domain, or your current
tunnel URL while testing) so the links in the email actually resolve
somewhere real — without it, links will be relative and likely won't open
correctly from an email client.

**What this does now:** packing an outgoing delivery for Job #X (the
LOADED checkoff step) automatically marks every currently-active inventory
entry under Job #X as shipped — it disappears from the "current inventory"
count and export from that point on. This is a **job-number-level** link,
not item-level: there's no shared SKU system between what arrived
(Incoming Inventory) and an outgoing ticket's line items, so packing a
delivery for a job clears everything logged under that job number, on the
assumption that what's shipping is what was received for it. If a job's
material arrives and ships in separate partial batches, that assumption
won't always hold — for those cases, the PM Portal's Inventory tab has a
manual **Mark Shipped** button per row for fine-grained correction.

I tested this directly: checking in material for two different jobs at two
different locations, then packing an outgoing delivery for only one of
them — confirmed that job's entry disappeared from the inventory while the
unrelated job's entry stayed untouched. Also tested the manual Mark Shipped
button and its permission restriction (PM/admin only, same as the export).

### Setting up the flag email (required before this works for real)

Email credentials live in `server/.env` (not in `server_config.json`, and
never committed to version control). Copy the example and fill in your
company's real SMTP details:

```bash
cd server
cp .env.example .env
# edit .env with your real mail server / account
```

Ask IT which SMTP server your company uses — common ones are
`smtp.office365.com` (Microsoft 365) or `smtp.gmail.com` (Google Workspace),
or a transactional service like SendGrid/SES/Mailgun if your company uses
one. Until `.env` has real values, the Flag button still files the photo
locally, but the email won't send — the app will tell the person flagging it
that the alert didn't go out, so nothing is silently lost.

**I tested the flag email end-to-end against a local test mail server in my
own sandbox** (to confirm the code correctly composes and sends the message
with the photo attached) — not against your real `PMteam@aes-energy.com`
inbox, since I don't have access to it and shouldn't be sending real test
emails to your company on your behalf. Once real SMTP credentials are in
`.env`, send yourself one test flag before trusting it in daily use.

### Both flows use the same job_number_pattern

Both flows use the same `job_number_pattern` in `server_config.json` — tune
it once and it applies to both packing slips and delivery tickets, unless you
want them handled differently, in which case let me know and I'll split them
into two separate patterns.

### If signal drops mid-flow

Every step of Incoming Inventory is resilient to bad signal — nothing is
lost, and it shows up on Home under **Incoming Inventory — Pending**:

- **Photo taken but scan couldn't reach the server** → saved, labeled
  "Waiting for signal." Tapping **Retry Now** on Home retries the scan
  automatically — no re-photographing needed.
- **Scan succeeded but you back out before confirming** (or the app closes) →
  saved, labeled "Needs review." This one is **not** auto-retried, since a
  human still needs to see and approve the job number — tap it in the queue
  to reopen the confirm screen right where you left off.
- **Confirm or Flag was submitted but the request failed** → saved, labeled
  "Filing (will retry)" / "Flagging (will retry)." These retry automatically
  with **Retry Now** since the decision was already made — no re-entry
  needed.

I tested all of this with a simulated offline/online cycle (scan fails →
retry succeeds → confirm fails → retry succeeds; flag fails → batch retry
succeeds) — confirmed each state transition and that Home's queue counts,
button enable/disable state, and "Review" vs "Pending" labeling all behave
correctly.

### Assigning a driver, and the "on the way" text with ETA

When a PM schedules a delivery, they now pick an **Assigned Driver** from a
dropdown (populated from registered driver accounts) and enter a
**Receiver Phone** number. This changes what the driver sees and does:

- On Home, "Scheduled Deliveries — Today" is now **"My Deliveries"** — it
  shows everything assigned to that driver specifically (not just today's),
  so they can see upcoming jobs ahead of time. A driver never sees another
  driver's deliveries.
- Tapping an unstarted delivery opens a **Start Delivery** screen instead of
  jumping straight to the ticket. Tapping **"I'm Heading There Now"**:
  - Captures the driver's live GPS location
  - Calculates a driving ETA to the site address
  - **Texts the receiver** that the driver is on the way, with the ETA if
    available
  - Then reveals **"Continue to Ticket"**, which opens the same
    checkbox/photos/signature screen as before
- If a driver reopens an already-started delivery, it goes straight to the
  ticket screen — the "on the way" text only sends once per delivery.

### Setting up SMS and ETA (two new external services)

Both are optional in the sense that the app **never breaks** without them —
starting a delivery always works; it just skips the text and/or ETA if
either isn't configured. But you'll want both for this to do what you asked:

**SMS (Twilio):**
1. Sign up at [twilio.com](https://www.twilio.com), buy or verify a phone
   number capable of sending SMS.
2. From the console dashboard, copy your Account SID and Auth Token.
3. Add to `server/.env`:
   ```
   TWILIO_ACCOUNT_SID=...
   TWILIO_AUTH_TOKEN=...
   TWILIO_FROM_NUMBER=+15551234567
   ```
4. **Trial accounts can only text phone numbers you've manually verified**
   in the Twilio console — fine for testing with your own phone, not usable
   for real receivers until you upgrade to a paid account.

**ETA (Google Maps Distance Matrix API):**
1. In Google Cloud Console, create a project (or use an existing one) and
   enable the **Distance Matrix API**.
2. Create an API key under Credentials.
3. **Billing must be enabled** on the project — Google requires a card on
   file even though there's a free monthly quota that covers light use.
4. Add to `server/.env`:
   ```
   GOOGLE_MAPS_API_KEY=...
   ```
5. ETA accuracy depends on the **site address** being a real, geocodable
   address — enter it carefully when scheduling a delivery.

### What I tested vs. what needs a real-world check

I tested the SMS and ETA modules directly against mocked responses (since I
don't have your Twilio or Google Maps credentials), confirming the request
format, the graceful "not configured" fallback, and the "missing phone
number" fallback all behave correctly. I tested the full driver-assignment
flow end-to-end against the running server — critically, confirming that a
driver **only** sees deliveries assigned to them, not anyone else's. I also
ran a simulated-browser test of the whole "My Deliveries → Start Delivery →
Continue to Ticket" flow on the driver side, and the PM portal's driver
dropdown and assignment fields.

What still needs verification with real accounts: an actual text arriving on
a real phone, and a real ETA calculation against a real address — I'd
suggest testing both with your own phone number and a known address before
trusting this for real deliveries.

## 11. Known limitations to test before relying on this

- **Handwriting OCR is imperfect.** If job numbers are ever handwritten
  rather than printed, digits can be misread (e.g. a `5` read as an `8`),
  filing a delivery under the wrong job. Test with real handwriting samples;
  consider spot-checking `needs_review_no_job_number` regularly at first.
- **`job_number_pattern` needs tuning** against your actual ticket format —
  see section 3.
- **Small-fleet assumptions:** this is built for 1–5 drivers with manual
  end-of-shift sync. If the fleet grows much larger or you want photos
  uploading continuously through the day instead of once at night, the sync
  logic (currently a manual button) would need to change to automatic
  background upload — let me know if that becomes relevant.
- I built and tested this with synthetic photos in a sandboxed environment
  (server logic, OCR, batching, and the incomplete/needs-review flows are all
  verified). I have not tested the installed PWA on a real iPhone/Android
  device, since that requires an actual phone and a live HTTPS server — do a
  short pilot with one driver before rolling out to the full team.
- **Incoming Inventory requires signal throughout the entire flow** — scan,
  confirm, pallets, and finalize each talk to the server immediately. There
  is no offline retry queue for this flow (unlike the ad-hoc delivery
  flow) — a deliberate trade-off given how many steps are now involved.
  Test it somewhere with a reliable connection.
- **Server-side session cleanup:** an in-progress Incoming Inventory scan
  (pages taken, job not yet confirmed, or confirmed but pallets/locations
  not yet finished) stays on the server until finalized. If someone starts
  a scan and never finishes it, that session lingers indefinitely. Fine for
  a pilot; worth adding a cleanup job before wider rollout.
- The flag email requires real SMTP credentials in `.env` (see section 9) —
  it will not send anything until that's configured.
- **Shared password is inherently weak.** Every account uses the same
  password by design (see section 8) — fine for a closed pilot, not for real
  production use without moving to per-user passwords or SSO.
- **No name collisions anymore** — accounts are keyed by email now, not
  name, so this is no longer a concern.
- I tested the full login system — unified email/password login, wrong-
  password rejection, role-based tile display (driver vs. admin/PM), user
  registration (including duplicate-email and invalid-role rejection),
  permission checks, and the offline cached-session fallback — using a
  simulated browser environment and directly against the running server. I
  have not tested it in a real phone browser yet; do that as part of your
  pilot.
- **SMS and ETA require Twilio and Google Maps accounts** you set up
  yourself (see section 9) — until then, starting a delivery still works,
  it just won't text the receiver or show an ETA.
- **No re-assignment UI yet.** If a delivery needs to move from one driver
  to another after being scheduled, that currently requires editing
  `schedule_store.json` directly or re-creating the delivery — worth adding
  an "edit" action to the PM portal table if reassignment turns out to be
  common.
- **RECEIVED column not wired up yet.** The generated ticket's layout
  matches the real paper form's three checkbox columns (LOADED, DELIVERED,
  RECEIVED), but only LOADED (warehouse packing) and DELIVERED (driver
  unloading) are backed by actual per-item checkboxes in the app today. The
  receiver's overall signature stands in for RECEIVED for now.
- **Inventory location log connects to Outgoing Inventory by job number.**
  Packing a delivery for Job #X automatically clears Job #X's active
  inventory entries — tested end-to-end, including that unrelated jobs are
  left untouched. Since there's no per-item SKU link between what arrived
  and what's on an outgoing ticket, this is job-number-level, not item-level
  — a manual "Mark Shipped" button in the PM Portal handles edge cases
  (partial shipments) the automatic link can't.
- **Role menu:** now always exactly three tiles (Driver, Warehouse, Project
  Management). Driver-type accounts see Driver + Warehouse; PM and admin
  accounts see all three. Tested via simulated browser across all account
  types. Not yet tested on a real phone.
- **Outgoing Inventory (packing) staging:** similar to Incoming Inventory,
  once Warehouse packs and signs an order there's no separate cleanup
  needed — the record just moves to "packed" status — but if a ticket is
  generated/uploaded and then never packed, it sits in "Ready to Pack"
  indefinitely with no reminder. Worth adding a nudge email for this if
  aging tickets become an issue.
- **Driver/warehouse account permissions:** PM and admin can now register
  drivers/PMs and reset codes directly from the PM Portal's Admin Tools tab
  (previously admin-only) — this was a deliberate relaxation to match "PM
  has access to everything." If that's broader access than you actually
  want PMs to have, let me know and I'll scope it back down.
- **New Incoming Inventory flow (multi-page, PO#, PM directory, pallets,
  split locations, QR code):** built and tested end-to-end against the
  running server — multi-page scanning, the job→PM directory (both the
  "new job needs a PM" path and the "remembered from before" path),
  pallet-count enforcement, location-split validation (rejecting mismatched
  totals), QR code generation (confirmed it actually decodes to the right
  link, not just that a file exists), and the daily report email content.
  Also ran a full simulated-browser test of the entire wizard UI. Two real
  gaps, not just caveats: (1) **no printer is connected yet** — the "Print
  QR Code" button opens a PDF for your device's own print dialog to handle,
  since no printer has been purchased; tell me the make/model once you
  have one and direct network printing is a reasonable next step. (2) the
  **PO number and job number OCR patterns are untested against your real
  packing slips** — same caveat as the original job-number pattern in
  section 3, now doubled since there are two patterns to tune.
- **Outbound workflow (Revise / Send to PM):** tested end-to-end against
  the running server — creating a ticket, revising it from the warehouse
  side before packing, sending a copy to a different PM than the one
  assigned, packing, then **revising again after packing** (confirmed it
  succeeds rather than being blocked, correctly resets to "needs re-packing"
  and reappears in the Ready to Pack queue), re-packing, starting the
  delivery, and **revising again while the driver is en route** (confirmed
  it succeeds and leaves the delivery's status untouched rather than
  yanking it back), and finally **revising after completion** (confirmed it
  succeeds as a record correction without un-completing the delivery).
  Every one of these fired the PM + warehouse alert email. Also ran a full
  simulated-browser test of both buttons on the phone's Ready to Pack list.
  Revising from the phone currently edits line items only (not header
  fields like customer/PO/job name) — those can still be edited via the
  same endpoint from the PM Portal, or say the word if you want a fuller
  header-editing UI added to the phone screen too.
