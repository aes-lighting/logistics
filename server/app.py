#!/usr/bin/env python3
"""
AES Logistics - server app

Serves the driver PWA (static files) and receives delivery photo uploads
from drivers' phones. Because the app itself tags each photo as "ticket" or
"pallet" and groups them by delivery at capture time, the server doesn't have
to guess anything the way the old folder-watching script did — it just reads
the job number off the ticket via OCR and files the whole delivery.

Endpoints:
    GET  /                       -> serves the driver PWA
    POST /api/upload             -> receives one delivery's photos + metadata (login required)
    GET  /api/health             -> health check

    Auth:
    POST /api/auth/driver_login   -> name + code; first use of a name registers it
    POST /api/auth/admin_login    -> fixed admin email + password (from .env)
    POST /api/auth/pm_login       -> PM email + password (admin-provisioned)
    POST /api/auth/logout         -> clears the session
    GET  /api/auth/me             -> current session identity, or 401
    POST /api/auth/admin/reset_driver_code -> admin-only, resets a driver's code
    POST /api/auth/admin/register_driver   -> admin-only, pre-registers a driver
    POST /api/auth/admin/register_pm       -> admin-only, creates a PM account

    Scheduled Delivery flow (calendar-linked, ticket + checkoff + signature):
    GET  /api/schedule/calendar/settings    -> get the ICS feed URL (PM/admin)
    POST /api/schedule/calendar/settings    -> set the ICS feed URL (PM/admin)
    GET  /api/schedule/calendar/upcoming    -> upcoming calendar events not yet set up (PM/admin)
    GET  /api/schedule                      -> list all scheduled deliveries (PM/admin)
    POST /api/schedule                      -> create a scheduled delivery (PM/admin)
    POST /api/schedule/<id>/ticket           -> upload the delivery ticket (PM/admin)
    GET  /api/schedule/<id>/file/<name>       -> serve a ticket/signature/photo file (any logged in role)
    GET  /api/schedule/driver/today          -> today's ready-to-deliver tickets (driver)
    POST /api/schedule/<id>/complete         -> checkoff + signature + photos + geotag (driver) -> emails PM + receiver

    Incoming Inventory (packing slip) flow — requires connectivity at scan
    time, unlike the delivery flow, because the job number is shown back to
    the person scanning for them to confirm/edit before it's filed. All
    require login:
    POST /api/incoming/scan       -> upload one packing slip photo, get OCR guess back
    POST /api/incoming/confirm    -> confirm/edit job number, file the slip
    POST /api/incoming/flag       -> flag a slip as having no/bad job number, emails PM team

Run (development):
    python3 app.py

Run (production): see README.md for gunicorn + nginx + HTTPS setup.
"""

import io
import json
import logging
import os
import re
import secrets
import shutil
import sys
import uuid
from datetime import datetime

from dotenv import load_dotenv
from flask import Flask, request, jsonify, send_from_directory, session, send_file

import auth
import emailer
import inventory
import inventory_report
import maps
import qr_ticket
import scheduling
import sms
import ticket_render

load_dotenv()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "server_config.json")
STATIC_DIR = os.path.join(BASE_DIR, "..", "driver_app")
PM_STATIC_DIR = os.path.join(BASE_DIR, "..", "pm_portal")

app = Flask(__name__, static_folder=None)

_secret_key = os.environ.get("FLASK_SECRET_KEY")
if not _secret_key:
    _secret_key = secrets.token_hex(32)
    print(
        "WARNING: FLASK_SECRET_KEY not set in .env — using a random key for this run only. "
        "Everyone will be logged out on every restart until you set a fixed one. "
        "Add FLASK_SECRET_KEY=<random string> to .env to fix this.",
        file=sys.stderr,
    )
app.secret_key = _secret_key
app.config.update(
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_HTTPONLY=True,
    PERMANENT_SESSION_LIFETIME=60 * 60 * 24 * 30,  # 30 days
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("aes_logistics")

auth.seed_admin_from_env()


def load_config():
    with open(CONFIG_PATH, "r") as f:
        cfg = json.load(f)
    cfg.setdefault("incoming_dir", os.path.join(BASE_DIR, "incoming"))
    cfg.setdefault("dest_dir", os.path.join(BASE_DIR, "organized"))
    cfg.setdefault("review_folder", "needs_review_no_job_number")
    cfg.setdefault("incomplete_flag_filename", "INCOMPLETE_missing_pallet_photo.txt")
    cfg.setdefault("incoming_staging_dir", os.path.join(BASE_DIR, "incoming", "_staging"))
    cfg.setdefault("incoming_slip_subfolder", "Incoming_Packing_Slips")
    cfg.setdefault("flagged_slips_folder", "flagged_packing_slips")
    cfg.setdefault("flag_alert_email_to", "PMteam@aes-energy.com")
    cfg.setdefault("warehouse_alert_email", "Warehouse@aes-energy.com")
    cfg.setdefault("po_number_pattern", r"p\.?\s*o\.?\s*#?\s*:?\s*(?P<po>[A-Za-z0-9\-]{3,20})")
    return cfg


CFG = load_config()
os.makedirs(CFG["incoming_dir"], exist_ok=True)
os.makedirs(CFG["dest_dir"], exist_ok=True)
os.makedirs(CFG["incoming_staging_dir"], exist_ok=True)


def ocr_text(filepath):
    import pytesseract
    from PIL import Image

    try:
        img = Image.open(filepath)
        return pytesseract.image_to_string(img)
    except Exception as e:
        log.warning(f"OCR failed on {filepath}: {e}")
        return ""


def extract_job_number(filepath, job_pattern):
    text = ocr_text(filepath)
    match = re.search(job_pattern, text, re.IGNORECASE)
    if match:
        job_number = match.groupdict().get("job") or match.group(0)
        return re.sub(r"\s+", "", job_number)
    return None


def extract_po_number(filepath, po_pattern):
    text = ocr_text(filepath)
    match = re.search(po_pattern, text, re.IGNORECASE)
    if match:
        po_number = match.groupdict().get("po") or match.group(0)
        return re.sub(r"\s+", "", po_number)
    return None


def unique_destination(dest_dir, filename):
    base, ext = os.path.splitext(filename)
    candidate = os.path.join(dest_dir, filename)
    counter = 1
    while os.path.exists(candidate):
        candidate = os.path.join(dest_dir, f"{base}_{counter}{ext}")
        counter += 1
    return candidate


def process_delivery(delivery_dir, metadata, cfg):
    """
    metadata = {
        "delivery_id": str,
        "driver": str,
        "completed_at": iso timestamp,
        "photos": [ {"filename": str, "type": "ticket"|"pallet"}, ... ]
    }
    Returns (job_number_or_None, dest_folder_path)
    """
    job_pattern = cfg["job_number_pattern"]
    photos = metadata.get("photos", [])

    ticket_files = [p["filename"] for p in photos if p.get("type") == "ticket"]
    has_pallet = any(p.get("type") == "pallet" for p in photos)

    job_number = None
    for fname in ticket_files:
        fpath = os.path.join(delivery_dir, fname)
        if os.path.isfile(fpath):
            job_number = extract_job_number(fpath, job_pattern)
            if job_number:
                break

    if not job_number:
        target_dir = os.path.join(cfg["dest_dir"], cfg["review_folder"], metadata.get("delivery_id", "unknown"))
    else:
        target_dir = os.path.join(cfg["dest_dir"], f"Job_{job_number}")

    os.makedirs(target_dir, exist_ok=True)

    for p in photos:
        fname = p["filename"]
        src = os.path.join(delivery_dir, fname)
        if not os.path.isfile(src):
            log.warning(f"Expected file missing from upload: {src}")
            continue
        dest = unique_destination(target_dir, fname)
        shutil.move(src, dest)
        log.info(f"Filed {fname} ({p.get('type')}) -> {dest}")

    if job_number and not has_pallet:
        flag_path = os.path.join(target_dir, cfg["incomplete_flag_filename"])
        with open(flag_path, "a") as f:
            f.write(
                f"Delivery {metadata.get('delivery_id')} by {metadata.get('driver')} "
                f"completed at {metadata.get('completed_at')} has a ticket but no "
                f"pallet/box photo.\n"
            )
        log.warning(f"INCOMPLETE: {target_dir} missing pallet/box photo.")

    # clean up the now-empty incoming delivery folder
    try:
        shutil.rmtree(delivery_dir)
    except OSError:
        pass

    return job_number, target_dir


@app.route("/", methods=["GET"])
def serve_app():
    return send_from_directory(STATIC_DIR, "index.html")


@app.route("/pm", methods=["GET"])
@app.route("/pm/", methods=["GET"])
def serve_pm_portal():
    return send_from_directory(PM_STATIC_DIR, "index.html")


@app.route("/pm/<path:filename>")
def serve_pm_static(filename):
    return send_from_directory(PM_STATIC_DIR, filename)


@app.route("/<path:filename>")
def serve_static(filename):
    return send_from_directory(STATIC_DIR, filename)


@app.route("/api/health")
def health():
    return jsonify({"status": "ok", "time": datetime.now().isoformat()})


@app.route("/api/upload", methods=["POST"])
@auth.login_required
def upload():
    """
    Expects multipart/form-data:
        - field "metadata": JSON string (see process_delivery docstring)
        - one file field per photo, field name == metadata photos[i].filename
    """
    cfg = load_config()  # reload each request so config edits apply without restart

    metadata_raw = request.form.get("metadata")
    if not metadata_raw:
        return jsonify({"error": "missing 'metadata' field"}), 400

    try:
        metadata = json.loads(metadata_raw)
    except json.JSONDecodeError as e:
        return jsonify({"error": f"invalid metadata JSON: {e}"}), 400

    delivery_id = metadata.get("delivery_id") or str(uuid.uuid4())
    metadata["delivery_id"] = delivery_id

    delivery_dir = os.path.join(cfg["incoming_dir"], delivery_id)
    os.makedirs(delivery_dir, exist_ok=True)

    saved = []
    for p in metadata.get("photos", []):
        fname = p["filename"]
        file_obj = request.files.get(fname)
        if file_obj is None:
            log.warning(f"Upload for delivery {delivery_id} missing file part: {fname}")
            continue
        save_path = os.path.join(delivery_dir, fname)
        file_obj.save(save_path)
        saved.append(fname)

    with open(os.path.join(delivery_dir, "metadata.json"), "w") as f:
        json.dump(metadata, f, indent=2)

    log.info(f"Received delivery {delivery_id} from {metadata.get('driver')}: {len(saved)} photo(s)")

    try:
        job_number, target_dir = process_delivery(delivery_dir, metadata, cfg)
    except Exception as e:
        log.error(f"Processing failed for delivery {delivery_id}: {e}")
        return jsonify({"error": "upload received but processing failed", "delivery_id": delivery_id}), 500

    return jsonify({
        "status": "ok",
        "delivery_id": delivery_id,
        "job_number": job_number,
        "filed_to": os.path.relpath(target_dir, cfg["dest_dir"]),
    })


### --- Incoming Inventory flow --- ###
# Redesigned as a multi-step session: scan one or more slip pages -> confirm
# job/PO number (auto-emails the job's PM, remembered per job after the
# first time) -> pallet count + one photo per pallet -> choose location(s),
# splittable across several -> comment -> finalize (logs to the running
# inventory ledger and generates a printable QR code).

def _session_dir(cfg, session_id):
    return os.path.join(cfg["incoming_staging_dir"], session_id)


def _load_session(cfg, session_id):
    meta_path = os.path.join(_session_dir(cfg, session_id), "metadata.json")
    if not os.path.isfile(meta_path):
        return None
    with open(meta_path, "r") as f:
        return json.load(f)


def _save_session(cfg, session_id, metadata):
    session_dir = _session_dir(cfg, session_id)
    os.makedirs(session_dir, exist_ok=True)
    with open(os.path.join(session_dir, "metadata.json"), "w") as f:
        json.dump(metadata, f, indent=2)


@app.route("/api/incoming/scan_page", methods=["POST"])
@auth.login_required
def api_incoming_scan_page():
    """
    Accepts one photo (field 'photo'). If 'session_id' (form field) isn't
    given, starts a new multi-page session. Each call adds one more page —
    this is how a multi-page packing slip is captured, one photo per page,
    before confirming the job number.
    """
    cfg = load_config()

    file_obj = request.files.get("photo")
    if file_obj is None:
        return jsonify({"error": "missing 'photo' file"}), 400

    session_id = request.form.get("session_id") or str(uuid.uuid4())
    metadata = _load_session(cfg, session_id) or {
        "job_number": None, "po_number": None, "pm_email": None, "staff": None,
        "slip_photo_filenames": [], "filed_slip_paths": [],
        "pallet_photo_filenames": [], "created_at": datetime.now().isoformat(),
    }

    page_num = len(metadata["slip_photo_filenames"]) + 1
    filename = f"page_{page_num}.jpg"
    save_path = os.path.join(_session_dir(cfg, session_id), filename)
    os.makedirs(_session_dir(cfg, session_id), exist_ok=True)
    file_obj.save(save_path)
    metadata["slip_photo_filenames"].append(filename)
    _save_session(cfg, session_id, metadata)

    job_guess = extract_job_number(save_path, cfg["job_number_pattern"])
    po_guess = extract_po_number(save_path, cfg["po_number_pattern"])

    log.info(f"Incoming session {session_id}: page {page_num} scanned, job_guess={job_guess}, po_guess={po_guess}")

    return jsonify({
        "session_id": session_id,
        "page_number": page_num,
        "job_number_guess": job_guess,
        "po_number_guess": po_guess,
    })


@app.route("/api/inventory/pms")
@auth.login_required
def api_inventory_pms():
    """List of registered PMs, for the 'which PM owns this job' picker (only needed the first time a job is seen)."""
    pms = [u for u in auth.list_users() if u["role"] == "pm"]
    return jsonify({"pms": pms})


@app.route("/api/incoming/confirm_job", methods=["POST"])
@auth.login_required
def api_incoming_confirm_job():
    """
    Body (JSON): { session_id, job_number, po_number, pm_email (optional), staff }
    Files the slip page(s) into the job folder and emails that job's PM with
    them attached. If this job number has never been seen before, pm_email
    is required (client should show a PM picker) — after that, it's
    remembered automatically for next time.
    """
    cfg = load_config()
    data = request.get_json(silent=True) or {}

    session_id = data.get("session_id")
    job_number = (data.get("job_number") or "").strip()
    po_number = (data.get("po_number") or "").strip()
    pm_email = (data.get("pm_email") or "").strip()
    staff = data.get("staff", "")

    if not session_id:
        return jsonify({"error": "missing 'session_id'"}), 400
    metadata = _load_session(cfg, session_id)
    if not metadata:
        return jsonify({"error": f"no scan session found for {session_id}"}), 404
    if not job_number:
        return jsonify({"error": "missing 'job_number'"}), 400

    existing_pm = inventory.get_pm_for_job(job_number)
    if existing_pm:
        pm_email = existing_pm
    elif not pm_email:
        return jsonify({
            "error": "needs_pm",
            "message": f"Job #{job_number} hasn't been seen before — pick which PM owns it.",
        }), 400
    else:
        inventory.set_pm_for_job(job_number, pm_email)

    job_number_clean = re.sub(r"\s+", "", job_number)
    target_dir = os.path.join(cfg["dest_dir"], f"Job_{job_number_clean}", cfg["incoming_slip_subfolder"])
    os.makedirs(target_dir, exist_ok=True)

    filed_paths = []
    session_dir = _session_dir(cfg, session_id)
    for fname in metadata["slip_photo_filenames"]:
        src = os.path.join(session_dir, fname)
        if os.path.isfile(src):
            dest = unique_destination(target_dir, fname)
            shutil.move(src, dest)
            filed_paths.append(dest)

    metadata["job_number"] = job_number_clean
    metadata["po_number"] = po_number
    metadata["pm_email"] = pm_email
    metadata["staff"] = staff
    metadata["filed_slip_paths"] = filed_paths
    _save_session(cfg, session_id, metadata)

    subject = f"[AES Logistics] Packing slip received — Job #{job_number_clean}" + (f" / PO {po_number}" if po_number else "")
    body = (
        f"A packing slip just arrived and was checked in.\n\n"
        f"Job number: {job_number_clean}\n"
        f"PO number: {po_number or '(not provided)'}\n"
        f"Checked in by: {staff or '(not provided)'}\n"
        f"Time: {datetime.now().isoformat()}\n"
        f"Pages: {len(filed_paths)}\n"
    )
    email_sent, email_error = emailer.send_flag_email(
        to_addr=pm_email, subject=subject, body_text=body, attachment_paths=filed_paths,
    )
    if not email_sent:
        log.warning(f"Could not email PM {pm_email} for job {job_number_clean}: {email_error}")

    log.info(f"Incoming session {session_id} confirmed as Job_{job_number_clean}, PM {pm_email}, email_sent={email_sent}")

    return jsonify({
        "status": "ok", "job_number": job_number_clean, "po_number": po_number,
        "pm_email": pm_email, "email_sent": email_sent, "email_error": email_error,
    })


@app.route("/api/incoming/pallet_photo", methods=["POST"])
@auth.login_required
def api_incoming_pallet_photo():
    """Accepts one pallet photo (field 'photo') for an in-progress session (form field 'session_id')."""
    cfg = load_config()
    session_id = request.form.get("session_id")
    file_obj = request.files.get("photo")
    if not session_id or file_obj is None:
        return jsonify({"error": "missing 'session_id' or 'photo'"}), 400

    metadata = _load_session(cfg, session_id)
    if not metadata:
        return jsonify({"error": f"no scan session found for {session_id}"}), 404

    pallet_num = len(metadata["pallet_photo_filenames"]) + 1
    filename = f"pallet_{pallet_num}.jpg"
    save_path = os.path.join(_session_dir(cfg, session_id), filename)
    file_obj.save(save_path)
    metadata["pallet_photo_filenames"].append(filename)
    _save_session(cfg, session_id, metadata)

    return jsonify({"status": "ok", "pallet_number": pallet_num, "filename": filename})


@app.route("/api/incoming/finalize", methods=["POST"])
@auth.login_required
def api_incoming_finalize():
    """
    Body (JSON): { session_id, pallet_count, locations: [{location, count}], comment }
    Logs the finished entry to the inventory ledger, files pallet photos
    into the job folder, generates a printable QR code, and cleans up the
    scan session.
    """
    cfg = load_config()
    data = request.get_json(silent=True) or {}

    session_id = data.get("session_id")
    pallet_count = data.get("pallet_count")
    locations = data.get("locations") or []
    comment = data.get("comment", "")

    if not session_id:
        return jsonify({"error": "missing 'session_id'"}), 400
    metadata = _load_session(cfg, session_id)
    if not metadata:
        return jsonify({"error": f"no scan session found for {session_id}"}), 404
    if not metadata.get("job_number"):
        return jsonify({"error": "Job number must be confirmed before finalizing (call confirm_job first)."}), 400

    try:
        pallet_count = int(pallet_count)
    except (TypeError, ValueError):
        return jsonify({"error": "'pallet_count' must be a number"}), 400

    if not locations:
        return jsonify({"error": "At least one location is required."}), 400
    for loc in locations:
        if loc.get("location") not in inventory.LOCATIONS:
            return jsonify({"error": f"'{loc.get('location')}' is not a valid location. Must be one of: {', '.join(inventory.LOCATIONS)}"}), 400
    location_total = sum(int(loc.get("count", 0)) for loc in locations)
    if location_total != pallet_count:
        return jsonify({"error": f"Location counts add up to {location_total}, but pallet count is {pallet_count} — they must match."}), 400

    job_number = metadata["job_number"]
    target_dir = os.path.join(cfg["dest_dir"], f"Job_{job_number}", "Pallet_Photos")
    os.makedirs(target_dir, exist_ok=True)

    session_dir = _session_dir(cfg, session_id)
    filed_pallet_filenames = []
    for fname in metadata["pallet_photo_filenames"]:
        src = os.path.join(session_dir, fname)
        if os.path.isfile(src):
            dest = unique_destination(target_dir, fname)
            shutil.move(src, dest)
            filed_pallet_filenames.append(os.path.basename(dest))

    entry = inventory.add_entry(
        job_number=job_number,
        po_number=metadata.get("po_number"),
        confirmed_by=metadata.get("staff"),
        slip_photo_filenames=[os.path.basename(p) for p in metadata.get("filed_slip_paths", [])],
        pm_email=metadata.get("pm_email"),
        pallet_count=pallet_count,
        pallet_photo_filenames=filed_pallet_filenames,
        locations=locations,
        comment=comment,
    )

    qr_bytes = qr_ticket.build_qr_pdf(
        entry_id=entry["id"], job_number=job_number, po_number=metadata.get("po_number"),
        base_url=request.host_url, locations=locations, pallet_count=pallet_count,
    )
    qr_dir = os.path.join(cfg["dest_dir"], f"Job_{job_number}")
    qr_filename = f"QR_{entry['id']}.pdf"
    with open(os.path.join(qr_dir, qr_filename), "wb") as f:
        f.write(qr_bytes)
    inventory.set_qr_pdf_filename(entry["id"], qr_filename)

    shutil.rmtree(session_dir, ignore_errors=True)

    log.info(f"Incoming session {session_id} finalized as entry {entry['id']} for Job_{job_number}")

    return jsonify({
        "status": "ok",
        "entry_id": entry["id"],
        "qr_pdf_url": f"/api/inventory/{entry['id']}/qr_pdf",
    })


@app.route("/api/inventory/<entry_id>/qr_pdf")
@auth.login_required
def api_inventory_qr_pdf(entry_id):
    entry = inventory.get_entry(entry_id)
    if not entry or not entry.get("qr_pdf_filename"):
        return jsonify({"error": "no QR PDF found for that entry"}), 404
    cfg = load_config()
    path = os.path.join(cfg["dest_dir"], f"Job_{entry['job_number']}", entry["qr_pdf_filename"])
    if not os.path.isfile(path):
        return jsonify({"error": "QR PDF file missing on disk"}), 404
    return send_file(path, mimetype="application/pdf")


@app.route("/api/inventory/<entry_id>")
@auth.login_required
def api_inventory_detail(entry_id):
    entry = inventory.get_entry(entry_id)
    if not entry:
        return jsonify({"error": "not found"}), 404
    return jsonify(entry)


@app.route("/api/incoming/flag", methods=["POST"])
@auth.login_required
def incoming_flag():
    """
    Body (JSON): { session_id, reason, note (optional), staff (optional) }
    Files whatever slip photos exist in this session under a flagged-slips
    folder and emails the PM team, instead of guessing a job number wrong.
    Can be called at any point in the flow — before or after confirm_job.
    """
    cfg = load_config()
    data = request.get_json(silent=True) or {}

    session_id = data.get("session_id")
    reason = data.get("reason", "No reason given")
    note = data.get("note", "")
    staff = data.get("staff", "")

    if not session_id:
        return jsonify({"error": "missing 'session_id'"}), 400
    metadata = _load_session(cfg, session_id)
    if not metadata:
        return jsonify({"error": f"no scan session found for {session_id}"}), 404

    target_dir = os.path.join(cfg["dest_dir"], cfg["flagged_slips_folder"], session_id)
    os.makedirs(target_dir, exist_ok=True)

    session_dir = _session_dir(cfg, session_id)
    filed = []
    # pages not yet filed (job not confirmed) live in the session dir directly
    for fname in metadata.get("slip_photo_filenames", []):
        src = os.path.join(session_dir, fname)
        if os.path.isfile(src):
            dest = unique_destination(target_dir, fname)
            shutil.move(src, dest)
            filed.append(dest)
    # pages already filed to a job folder (job was confirmed, then something else went wrong)
    for src in metadata.get("filed_slip_paths", []):
        if os.path.isfile(src):
            dest = unique_destination(target_dir, os.path.basename(src))
            shutil.move(src, dest)
            filed.append(dest)

    shutil.rmtree(session_dir, ignore_errors=True)

    subject = f"[AES Logistics] Flagged packing slip — {reason}"
    body = (
        f"A packing slip was flagged and needs review.\n\n"
        f"Reason: {reason}\n"
        f"Note: {note or '(none)'}\n"
        f"Flagged by: {staff or '(not provided)'}\n"
        f"Time: {datetime.now().isoformat()}\n"
    )
    email_sent, email_error = emailer.send_flag_email(
        to_addr=cfg["flag_alert_email_to"], subject=subject, body_text=body,
        attachment_paths=filed,
    )

    log.warning(f"Flagged incoming session {session_id} ({reason}) — email_sent={email_sent}")

    return jsonify({"status": "ok", "email_sent": email_sent, "email_error": email_error})


### --- Auth --- ###

@app.route("/api/auth/login", methods=["POST"])
def api_login():
    data = request.get_json(silent=True) or {}
    status, body = auth.login(data.get("email"), data.get("password"))
    if status == 200:
        session.permanent = True
    return jsonify(body), status


@app.route("/api/auth/logout", methods=["POST"])
def api_logout():
    session.clear()
    return jsonify({"status": "ok"})


@app.route("/api/auth/me")
def api_me():
    identity = auth.current_session()
    if not identity:
        return jsonify({"error": "not logged in"}), 401
    return jsonify(identity)


@app.route("/api/auth/admin/register_user", methods=["POST"])
@auth.pm_or_admin_required
def api_admin_register_user():
    data = request.get_json(silent=True) or {}
    status, body = auth.register_user(data.get("name"), data.get("email"), data.get("role"))
    return jsonify(body), status


@app.route("/api/auth/admin/users")
@auth.pm_or_admin_required
def api_admin_list_users():
    return jsonify({"users": auth.list_users()})


### --- Scheduled Delivery flow --- ###

@app.route("/api/schedule/calendar/settings", methods=["GET"])
@auth.pm_or_admin_required
def api_get_calendar_settings():
    return jsonify({"ics_url": scheduling.get_ics_url()})


@app.route("/api/schedule/calendar/settings", methods=["POST"])
@auth.pm_or_admin_required
def api_set_calendar_settings():
    data = request.get_json(silent=True) or {}
    scheduling.set_ics_url(data.get("ics_url"))
    return jsonify({"status": "ok"})


@app.route("/api/schedule/calendar/upcoming")
@auth.pm_or_admin_required
def api_calendar_upcoming():
    events = scheduling.fetch_upcoming_events()
    linked = scheduling.linked_event_uids()
    for e in events:
        e["already_scheduled"] = e["uid"] in linked
    return jsonify({"events": events})


@app.route("/api/schedule", methods=["GET"])
@auth.pm_or_admin_required
def api_list_schedule():
    return jsonify({"deliveries": scheduling.list_deliveries()})


@app.route("/api/schedule", methods=["POST"])
@auth.pm_or_admin_required
def api_create_schedule():
    data = request.get_json(silent=True) or {}
    required = ["job_number", "delivery_date", "receiver_name", "receiver_email", "pm_email"]
    missing = [k for k in required if not data.get(k)]
    if missing:
        return jsonify({"error": f"Missing required field(s): {', '.join(missing)}"}), 400

    record = scheduling.create_delivery(
        job_number=data["job_number"],
        delivery_date=data["delivery_date"],
        receiver_name=data["receiver_name"],
        receiver_email=data["receiver_email"],
        pm_email=data["pm_email"],
        site_address=data.get("site_address", ""),
        calendar_event_uid=data.get("calendar_event_uid"),
        assigned_driver=data.get("assigned_driver"),
        receiver_phone=data.get("receiver_phone"),
        customer_name=data.get("customer_name", ""),
        customer_po=data.get("customer_po", ""),
        job_name=data.get("job_name", ""),
        delivery_method=data.get("delivery_method", ""),
    )
    return jsonify(record)


@app.route("/api/schedule/drivers")
@auth.pm_or_admin_required
def api_schedule_drivers():
    """List of registered driver/warehouse names, for the PM portal's assignment dropdown."""
    drivers = [u for u in auth.list_users() if u["role"] == "driver"]
    return jsonify({"drivers": drivers})


@app.route("/api/schedule/<delivery_id>/ticket", methods=["POST"])
@auth.pm_or_admin_required
def api_upload_ticket(delivery_id):
    file_obj = request.files.get("ticket")
    if file_obj is None:
        return jsonify({"error": "missing 'ticket' file"}), 400
    path = scheduling.save_ticket_file(delivery_id, file_obj)
    if not path:
        return jsonify({"error": f"no scheduled delivery found for id {delivery_id}"}), 404
    log.info(f"Ticket uploaded for scheduled delivery {delivery_id}")
    return jsonify({"status": "ok", "delivery": scheduling.get_delivery(delivery_id)})


@app.route("/api/schedule/<delivery_id>/generate_ticket", methods=["POST"])
@auth.pm_or_admin_required
def api_generate_ticket(delivery_id):
    """PM fills in line items; server renders a ticket image from the delivery's
    existing job/receiver info plus these items, and files it exactly like an
    uploaded ticket would be."""
    delivery = scheduling.get_delivery(delivery_id)
    if not delivery:
        return jsonify({"error": f"no scheduled delivery found for id {delivery_id}"}), 404

    data = request.get_json(silent=True) or {}
    line_items = data.get("line_items") or []
    if not isinstance(line_items, list) or not all(isinstance(i, dict) for i in line_items):
        return jsonify({"error": "line_items must be a list of {description, quantity, ...} objects"}), 400

    pm_name = auth.current_session().get("name") or session.get("email", "")

    image_bytes = ticket_render.render_ticket_image(
        job_number=delivery["job_number"],
        delivery_date=delivery["delivery_date"],
        receiver_name=delivery["receiver_name"],
        receiver_email=delivery["receiver_email"],
        site_address=delivery.get("site_address", ""),
        line_items=line_items,
        customer_name=delivery.get("customer_name", ""),
        customer_po=delivery.get("customer_po", ""),
        job_name=delivery.get("job_name", ""),
        delivery_method=delivery.get("delivery_method", ""),
        pm_name=pm_name,
    )
    record = scheduling.save_generated_ticket(delivery_id, image_bytes, line_items, pm_name=pm_name)
    log.info(f"Ticket generated for scheduled delivery {delivery_id} with {len(line_items)} line item(s)")
    return jsonify({"status": "ok", "delivery": record})


@app.route("/api/schedule/<delivery_id>/revise_ticket", methods=["POST"])
@auth.login_required
def api_revise_ticket(delivery_id):
    """
    Edits an existing ticket's line items/header fields and regenerates it.
    Always allowed, at any stage — see scheduling.revise_ticket's docstring
    for exactly how the record reacts depending on how far along the
    delivery already is. Always emails the assigned PM and a warehouse
    alert address with the updated ticket, flagging that it changed.
    Available to any logged-in role (PM, admin, or warehouse) since a
    warehouse worker may be the one who spots something wrong.
    """
    delivery = scheduling.get_delivery(delivery_id)
    if not delivery:
        return jsonify({"error": f"no scheduled delivery found for id {delivery_id}"}), 404

    data = request.get_json(silent=True) or {}
    line_items = data.get("line_items") or []
    if not isinstance(line_items, list) or not all(isinstance(i, dict) for i in line_items):
        return jsonify({"error": "line_items must be a list of {description, quantity, ...} objects"}), 400

    header_fields = {
        k: data[k] for k in ("customer_name", "customer_po", "job_name", "delivery_method", "site_address")
        if k in data
    }

    cfg = load_config()
    merged = {**delivery, **header_fields}

    image_bytes = ticket_render.render_ticket_image(
        job_number=merged["job_number"],
        delivery_date=merged["delivery_date"],
        receiver_name=merged["receiver_name"],
        receiver_email=merged["receiver_email"],
        site_address=merged.get("site_address", ""),
        line_items=line_items,
        customer_name=merged.get("customer_name", ""),
        customer_po=merged.get("customer_po", ""),
        job_name=merged.get("job_name", ""),
        delivery_method=merged.get("delivery_method", ""),
        pm_name=merged.get("pm_name", ""),
    )
    record, reset_to_pack = scheduling.revise_ticket(delivery_id, image_bytes, line_items, header_fields=header_fields)
    if not record:
        return jsonify({"error": f"no scheduled delivery found for id {delivery_id}"}), 404

    ticket_path = scheduling.ticket_file_path(delivery_id)
    revised_by = auth.current_session().get("name") or session.get("email", "")
    subject = f"[AES Logistics] Delivery ticket REVISED — Job #{record['job_number']}"

    stage_note = ""
    if reset_to_pack:
        stage_note = (
            "\nThis delivery had already been packed — since the checked-off items no longer "
            "match the revised ticket, it has been reset and needs to be re-packed and "
            "re-verified before a driver can take it.\n"
        )
    elif record["status"] == "en_route":
        stage_note = "\nHeads up: the driver is already en route for this delivery — please coordinate directly if this change matters before drop-off.\n"
    elif record["status"] == "completed":
        stage_note = "\nHeads up: this delivery was already marked completed — this revision is a record correction after the fact.\n"

    body = (
        f"The delivery ticket for Job #{record['job_number']} has been revised — please use the "
        f"attached updated version.\n\n"
        f"Revised by: {revised_by}\n"
        f"Revision #{record['revision_count']}\n"
        f"Time: {record['last_revised_at']}\n"
        f"{stage_note}"
    )
    recipients = [addr for addr in [record.get("pm_email"), cfg["warehouse_alert_email"]] if addr]
    for to_addr in recipients:
        sent, err = emailer.send_flag_email(to_addr=to_addr, subject=subject, body_text=body, attachment_path=ticket_path)
        if not sent:
            log.warning(f"Could not email revised ticket to {to_addr}: {err}")

    log.info(f"Ticket revised for delivery {delivery_id} (revision #{record['revision_count']}) by {revised_by}, reset_to_pack={reset_to_pack}")
    return jsonify({"status": "ok", "delivery": record, "reset_to_pack": reset_to_pack})


@app.route("/api/schedule/<delivery_id>/send_to_pm", methods=["POST"])
@auth.login_required
def api_send_to_pm(delivery_id):
    """Manually emails a copy of the current ticket to any chosen PM — independent of who's already assigned to the job."""
    delivery = scheduling.get_delivery(delivery_id)
    if not delivery:
        return jsonify({"error": f"no scheduled delivery found for id {delivery_id}"}), 404
    if not delivery.get("ticket_filename"):
        return jsonify({"error": "This delivery doesn't have a ticket yet."}), 400

    data = request.get_json(silent=True) or {}
    pm_email = (data.get("pm_email") or "").strip()
    if not pm_email:
        return jsonify({"error": "missing 'pm_email'"}), 400

    ticket_path = scheduling.ticket_file_path(delivery_id)
    sender = auth.current_session().get("name") or session.get("email", "")
    subject = f"[AES Logistics] Delivery ticket — Job #{delivery['job_number']}"
    body = (
        f"A copy of the delivery ticket for Job #{delivery['job_number']} was sent to you.\n\n"
        f"Sent by: {sender}\n"
        f"Time: {datetime.now().isoformat()}\n"
    )
    sent, err = emailer.send_flag_email(to_addr=pm_email, subject=subject, body_text=body, attachment_path=ticket_path)
    if not sent:
        log.warning(f"Could not send ticket to {pm_email}: {err}")

    log.info(f"Ticket for delivery {delivery_id} manually sent to {pm_email} by {sender}, sent={sent}")
    return jsonify({"status": "ok", "sent": sent, "error": err})


@app.route("/api/schedule/<delivery_id>/file/<filename>")
@auth.login_required
def api_schedule_file(delivery_id, filename):
    path = scheduling.delivery_file_path(delivery_id, filename)
    if not os.path.isfile(path):
        return jsonify({"error": "file not found"}), 404
    return send_file(path)


@app.route("/api/schedule/warehouse/ready_to_pack")
@auth.login_required
def api_schedule_ready_to_pack():
    """Outgoing Inventory queue: tickets that exist but haven't been packed/signed yet."""
    return jsonify({"deliveries": scheduling.deliveries_ready_to_pack()})


@app.route("/api/schedule/<delivery_id>/pack", methods=["POST"])
@auth.login_required
def api_schedule_pack(delivery_id):
    """
    Warehouse's outgoing-inventory step. If the delivery has line items,
    every item must be checked off (line_item_checks, a JSON array of bools
    matching the item list). If there are no line items (an uploaded photo
    ticket with nothing structured to check), a single overall
    'checkoff_confirmed' flag is used instead.
    """
    delivery = scheduling.get_delivery(delivery_id)
    if not delivery:
        return jsonify({"error": f"no scheduled delivery found for id {delivery_id}"}), 404

    packed_by = request.form.get("packed_by", "").strip()
    if not packed_by:
        return jsonify({"error": "Missing packer's name."}), 400

    signature_file = request.files.get("signature")
    if signature_file is None:
        return jsonify({"error": "missing 'signature' file"}), 400

    line_items = delivery.get("line_items") or []

    if line_items:
        checks_raw = request.form.get("line_item_checks")
        try:
            checks = json.loads(checks_raw) if checks_raw else []
        except json.JSONDecodeError:
            return jsonify({"error": "line_item_checks must be a JSON array"}), 400
        if len(checks) != len(line_items):
            return jsonify({"error": f"Expected {len(line_items)} check values, got {len(checks)}."}), 400
        if not all(checks):
            return jsonify({"error": "All line items must be checked off before packing is complete."}), 400
    else:
        checks = []
        if request.form.get("checkoff_confirmed") != "true":
            return jsonify({"error": "Checkoff must be confirmed before packing is complete."}), 400

    record = scheduling.pack_delivery(delivery_id, checks, packed_by, signature_file)

    # Packing an outgoing delivery for this job means that job's stored
    # material is leaving the warehouse — clear it from the active
    # inventory location log. See mark_removed_by_job's docstring for why
    # this is a job-number-level link rather than per-item.
    removed_count = inventory.mark_removed_by_job(delivery["job_number"])

    log.info(f"Delivery {delivery_id} packed by {packed_by}; {removed_count} inventory entr(ies) marked shipped for Job #{delivery['job_number']}")
    return jsonify({"status": "ok", "delivery": record, "inventory_entries_shipped": removed_count})


@app.route("/api/schedule/driver/today")
@auth.login_required
def api_schedule_driver_today():
    return jsonify({"deliveries": scheduling.deliveries_ready_for_driver()})


@app.route("/api/schedule/driver/mine")
@auth.login_required
def api_schedule_driver_mine():
    """A driver's full assigned list — not just today's — for the 'My Deliveries' menu."""
    driver_name = session.get("name")
    return jsonify({"deliveries": scheduling.deliveries_assigned_to(driver_name)})


@app.route("/api/schedule/<delivery_id>/start", methods=["POST"])
@auth.login_required
def api_schedule_start(delivery_id):
    """
    Driver taps 'Start This Delivery'. Computes an ETA (best-effort) and
    texts the receiver that the driver is on the way. Never blocks on either
    the maps lookup or the SMS send failing — a delivery can always start.
    """
    delivery = scheduling.get_delivery(delivery_id)
    if not delivery:
        return jsonify({"error": f"no scheduled delivery found for id {delivery_id}"}), 404

    data = request.get_json(silent=True) or {}
    lat = data.get("latitude")
    lng = data.get("longitude")

    eta = maps.get_eta(lat, lng, delivery.get("site_address")) if (lat is not None and lng is not None) else None

    if eta:
        eta_line = f" Estimated arrival: {eta['duration_text']} from now."
    else:
        eta_line = " (ETA unavailable right now.)"

    sms_body = (
        f"Hi {delivery['receiver_name']}, this is AES Logistics — our driver is on the way "
        f"for Job #{delivery['job_number']}.{eta_line}"
    )
    sms_sent, sms_error = sms.send_sms(delivery.get("receiver_phone"), sms_body)
    if not sms_sent:
        log.warning(f"Could not text receiver for delivery {delivery_id}: {sms_error}")

    record = scheduling.start_delivery(delivery_id, eta)
    log.info(f"Delivery {delivery_id} started by driver {session.get('name')}. SMS sent: {sms_sent}. ETA: {eta}")

    return jsonify({
        "status": "ok",
        "delivery": record,
        "sms_sent": sms_sent,
        "sms_error": sms_error,
        "eta": eta,
    })


@app.route("/api/schedule/<delivery_id>/complete", methods=["POST"])
@auth.login_required
def api_schedule_complete(delivery_id):
    delivery = scheduling.get_delivery(delivery_id)
    if not delivery:
        return jsonify({"error": f"no scheduled delivery found for id {delivery_id}"}), 404

    signed_by = request.form.get("signed_by", "")
    geotag_raw = request.form.get("geotag")
    geotag = json.loads(geotag_raw) if geotag_raw else None

    line_items = delivery.get("line_items") or []
    checkoff_confirmed = False
    unload_item_checks = []

    if line_items:
        checks_raw = request.form.get("unload_item_checks")
        try:
            unload_item_checks = json.loads(checks_raw) if checks_raw else []
        except json.JSONDecodeError:
            return jsonify({"error": "unload_item_checks must be a JSON array"}), 400
        if len(unload_item_checks) != len(line_items):
            return jsonify({"error": f"Expected {len(line_items)} check values, got {len(unload_item_checks)}."}), 400
        if not all(unload_item_checks):
            return jsonify({"error": "All items must be checked off as unloaded before completing."}), 400
        checkoff_confirmed = True
    else:
        checkoff_confirmed = request.form.get("checkoff_confirmed") == "true"
        if not checkoff_confirmed:
            return jsonify({"error": "Checkoff must be confirmed before completing."}), 400

    if not signed_by:
        return jsonify({"error": "Missing receiver signature name."}), 400

    signature_file = request.files.get("signature")
    if signature_file is None:
        return jsonify({"error": "missing 'signature' file"}), 400

    photo_files = request.files.getlist("photos")
    if len(photo_files) < 2:
        return jsonify({"error": "At least 2 photos of the material are required."}), 400

    record = scheduling.complete_delivery(
        delivery_id=delivery_id,
        checkoff_confirmed=checkoff_confirmed,
        signed_by=signed_by,
        signature_file_storage=signature_file,
        photo_file_storages=photo_files,
        geotag=geotag,
        unload_item_checks=unload_item_checks,
    )

    # Email the signed result to both the PM and the receiver.
    geotag_line = (
        f"Location at signing: {geotag['latitude']}, {geotag['longitude']} "
        f"(https://maps.google.com/?q={geotag['latitude']},{geotag['longitude']})\n"
        if geotag else "Location at signing: not available (device location was off or denied)\n"
    )
    body = (
        f"Delivery for Job #{delivery['job_number']} has been completed and signed for.\n\n"
        f"Signed by: {signed_by}\n"
        f"Completed at: {record['completed_at']}\n"
        f"{geotag_line}"
        f"Photos of material taken before leaving: {len(record['photo_filenames'])}\n"
    )

    ticket_path = scheduling.ticket_file_path(delivery_id)
    signature_path = scheduling.delivery_file_path(delivery_id, record["signature_filename"])
    photo_paths = [scheduling.delivery_file_path(delivery_id, p) for p in record["photo_filenames"]]

    for recipient in [delivery["pm_email"], delivery["receiver_email"]]:
        sent, err = emailer.send_flag_email(
            to_addr=recipient,
            subject=f"[AES Logistics] Signed delivery ticket — Job #{delivery['job_number']}",
            body_text=body,
            attachment_paths=[ticket_path, signature_path] + photo_paths,
        )
        if not sent:
            log.error(f"Failed to email signed ticket to {recipient}: {err}")

    log.info(f"Scheduled delivery {delivery_id} completed and emailed to PM + receiver.")
    return jsonify({"status": "ok", "delivery": record})


### --- Inventory (location tracking + Excel report) --- ###

@app.route("/api/inventory/locations")
@auth.login_required
def api_inventory_locations():
    return jsonify({"locations": inventory.LOCATIONS})


@app.route("/api/inventory")
@auth.login_required
def api_inventory_list():
    return jsonify({"entries": inventory.list_entries()})


@app.route("/api/inventory/<entry_id>/remove", methods=["POST"])
@auth.pm_or_admin_required
def api_inventory_remove(entry_id):
    """Manual removal — a safety valve for partial shipments or corrections
    that the automatic job-number-based removal (on packing) can't handle."""
    entry = inventory.mark_removed(entry_id)
    if not entry:
        return jsonify({"error": f"no inventory entry found for id {entry_id}"}), 404
    return jsonify({"status": "ok", "entry": entry})


@app.route("/api/inventory/export")
@auth.pm_or_admin_required
def api_inventory_export():
    report_bytes = inventory_report.build_report()
    filename = f"AES_Inventory_{datetime.now().strftime('%Y-%m-%d')}.xlsx"
    return send_file(
        io.BytesIO(report_bytes),
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name=filename,
    )


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
