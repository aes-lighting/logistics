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
   - **Driver-type accounts** (self-service PIN) see Driver + Warehouse —
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

The app requires logging in before anything else is usable. Two kinds of accounts:

**Driver / warehouse staff — self-service, no setup needed.** The first
time someone types a name and a code together, that code becomes theirs
from then on — nothing to pre-register. The code can be a 6-digit PIN, a
word, whatever they'll remember (minimum 4 characters). Get the name wrong
and it'll try to register a *new* account under that spelling, so encourage
people to use a consistent name (e.g. "Mike R." every time, not sometimes
"Mike" and sometimes "M. Rodriguez").

**Admin — one fixed account.** Credentials come from `server/.env`
(`ADMIN_EMAIL` / `ADMIN_PASSWORD`), never from `server_config.json` and
never hardcoded in the source. On every server start, if those two env vars
are set, the admin account is (re)synced to match them — so **changing the
admin password later is just: edit `.env`, restart the server.**

### Setting up the admin account for this pilot

```bash
cd server
cp .env.example .env
# then edit .env and set:
#   ADMIN_EMAIL=Wkennedy@aes-energy.com
#   ADMIN_PASSWORD=<a real password>
```

**Important:** the password you gave me in our conversation
(`AESgreen123!`) has now been typed in plaintext into a chat log, which
means I'd treat it as already exposed rather than truly secret. I've wired
the system to work with it for initial testing, but I'd strongly recommend
logging in once to confirm everything works, then changing it to something
new via the `.env` + restart process above before this goes anywhere near
real use. The password is never stored in plaintext on the server itself —
it's hashed the moment the server starts — but the copy that lived in this
chat is out of your control once typed.

### Where user management lives now

**Admin Tools moved into the PM Portal** (`/pm` → Admin Tools tab), since PM
accounts now have full access to everything and it made more sense as a
desk-oriented management page than a phone-app screen. Both admin and PM
logins can:
- **Register a driver/warehouse user** — set up a name + PIN/code before
  their first shift.
- **Register a Project Manager** — create a PM login (name, email, initial
  password).
- **Reset a driver's code** — for when someone forgets theirs.
- See live lists of everyone currently registered.

### Staying logged in

Once logged in, a session is remembered for 30 days (a signed cookie, not
stored in plaintext) so drivers don't need to log in every single delivery.
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

A second flow, separate from deliveries, for checking in incoming packing
slips. It works differently on purpose: since the person scanning needs to
**see and confirm/edit the job number** right after taking the photo, this
flow talks to the server immediately rather than queuing for an end-of-shift
sync. **It requires signal at scan time.**

Flow on the phone:
1. From Home, tap **+ Incoming Inventory**.
2. Take a photo of the packing slip.
3. The app uploads it immediately and shows "Reading job number…" while the
   server OCRs it.
4. The detected job number appears in an **editable field** — confirm it or
   correct it if OCR got it wrong.
5. **Select which warehouse/area this is going to** — Warehouse, Tent 1,
   Tent 2, or Econoboxes. Required before it can be confirmed.
6. Tap **Confirm & File** → the slip is filed to
   `organized/Job_<number>/Incoming_Packing_Slips/`, **and** a new entry is
   logged in the running inventory with that location.
7. If no job number could be read (or something else is wrong with the slip),
   tap **Flag — No Job Number / Issue** instead. Pick a reason (missing
   number, illegible, damaged, other), optionally add a note, and tap
   **Send Flag to PM Team**. This:
   - Files the photo to `organized/flagged_packing_slips/<id>/`
   - **Emails PMteam@aes-energy.com** with the reason, note, and the photo attached
   - (Flagged items are not logged to the location inventory, since there's
     no confirmed job number to attach them to.)

### Running inventory report (Excel)

Every confirmed Incoming Inventory check-in is logged — job number,
location, who confirmed it, and when — building up a live record of what's
been received and roughly where it physically is. This is separate from the
job folders on disk; it's a location ledger, not a file cabinet.

**PM Portal → Inventory tab** shows this as a live table, and an
**Export to Excel** button downloads a `.xlsx` report with two sheets:
- **Current Inventory** — every item, its location, who checked it in, and
  when — ready to open, filter, or print.
- **Summary by Location** — a count of items currently at each of the four
  locations, plus a total.

This is a snapshot at the moment of export, not a live-linked spreadsheet —
re-export anytime for a fresh copy. Available to PM and admin logins; any
logged-in role can view the table itself, but the export button is
PM/admin-only.

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
- **Incoming Inventory requires signal to actually reach the server** — but
  nothing is lost if signal drops; see the retry queue section above.
- **Server-side staging cleanup:** once a scan succeeds, the photo is staged
  on the server waiting for confirm/flag. The retry queue handles this fine
  as long as the app is opened again — but if a phone is lost or the app is
  never reopened, that staged photo lingers on the server indefinitely.
  Fine for a pilot; worth adding a cleanup job before wider rollout.
- The flag email requires real SMTP credentials in `.env` (see section 9) —
  it will not send anything until that's configured.
- **No self-service "forgot code" flow.** If a driver forgets their code,
  only an admin can reset it (Admin Tools). Worth adding a lighter-weight
  recovery option if this becomes a frequent support request.
- **Name collisions.** Driver accounts are keyed by name (case-insensitive).
  Two different people typing the same name would share one account and
  code. Fine for a small named fleet; would need real usernames/emails if
  the team grows or names could collide.
- I tested the full login system — driver self-registration, wrong-code
  rejection, admin login with the real credentials provided, admin-only
  user registration (including the duplicate-name safety check), admin-only
  code reset, and the offline cached-session fallback — using a simulated
  browser environment and directly against the running server. I have not
  tested it in a real phone browser yet; do that as part of your pilot.
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
