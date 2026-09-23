#!/usr/bin/env python3
"""
AES Logistics - server app

Serves the driver PWA (static files) and receives delivery photo uploads
from drivers' phones. Because the app itself tags each photo as "ticket" or
"pallet" and groups them by delivery at capture time, the server doesn't have
to guess anything the way the old folder-watching script did — it just reads
the job number off the ticket via OCR and files the whole delivery.

NOW INTEGRATED: completed-delivery photos/signature and received packing
slips + pallet photos are mirrored to the AES File Service (AES_API_URL,
POST /api/upload) into the job's project folder.

Endpoints:
    GET  /                       -> serves the driver PWA
    POST /api/upload             -> receives one delivery's photos + metadata (login required)
    GET  /api/health             -> health check

    Auth (via auth_routes.py Blueprint):
    POST /api/auth/login          -> email + password; proxies to auth-service
    POST /api/auth/logout         -> clears client-side auth
    GET  /api/auth/me             -> current user from Authorization header

    Scheduled Delivery flow (calendar-linked, ticket + checkoff + signature):
    GET  /api/schedule/calendar/settings    -> get the ICS feed URL (PM/admin)
    POST /api/schedule/calendar/settings    -> set the ICS feed URL (PM/admin)
    GET  /api/schedule/calendar/upcoming    -> upcoming calendar events not yet set up (PM/admin)
    GET  /api/schedule                      -> list all scheduled deliveries (PM/admin)
    POST /api/schedule                      -> create a scheduled delivery (PM/admin)
    POST /api/schedule/<id>/ticket           -> upload the delivery ticket (PM/admin)
    GET  /api/schedule/<id>/file/<n>       -> serve a ticket/signature/photo file (any logged in role)
    GET  /api/schedule/driver/today          -> today's ready-to-deliver tickets (driver)
    POST /api/schedule/<id>/complete         -> checkoff + signature + photos + geotag (driver) -> emails PM + receiver

    Incoming Inventory (packing slip) flow — requires connectivity at scan
    time, unlike the delivery flow, because the job number is shown back to
    the person scanning for them to confirm/edit before it's filed. All
    require login:
    POST /api/incoming/scan       -> upload one packing slip photo, get OCR guess back
    POST /api/incoming/confirm    -> confirm/edit job number, file the slip
    POST /api/incoming/flag       -> flag a slip (legacy slip_id or wizard session_id), emails PM team

    Incoming Inventory wizard (what driver_app actually calls; spec 005):
    POST /api/incoming/scan_page     -> add a slip page to a session, OCR guesses back
    POST /api/incoming/confirm_job   -> confirm job/PO + resolve PM (400 needs_pm if unknown)
    POST /api/incoming/pallet_photo  -> one photo per pallet
    POST /api/incoming/finalize      -> locations split + comment -> ledger entry, QR PDF, PM email
    GET  /api/inventory/<id>/qr.pdf  -> printable QR receiving label

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
from functools import wraps

from dotenv import load_dotenv
from flask import Flask, request, jsonify, send_from_directory, send_file
import requests

import emailer
import inventory
import inventory_report
import maps
import qr_ticket
import scheduling
import sms
import ticket_render
from auth_utils import get_auth_header, AUTH_SERVICE_URL, call_auth_service
from auth_decorators import login_required, admin_required, pm_or_admin_required
from auth_routes import auth_bp

load_dotenv()

# ===== Path Configuration =====
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "server_config.json")
STATIC_DIR = os.path.abspath(os.path.join(BASE_DIR, "..", "driver_app"))
PM_STATIC_DIR = os.path.abspath(os.path.join(BASE_DIR, "..", "pm_portal"))

# Debug: Print paths on startup
print(f"STATIC_DIR: {STATIC_DIR}")
print(f"PM_STATIC_DIR: {PM_STATIC_DIR}")
if os.path.isdir(STATIC_DIR):
    print(f"Files in STATIC_DIR: {os.listdir(STATIC_DIR)}")

# ===== AES File Service Configuration =====
# Secrets must come from the environment ONLY — never a hardcoded fallback.
# Fail fast at startup if the File Service key is missing so a misconfigured
# deploy can't silently run without auth to the file service.
AES_API_URL = os.environ.get("AES_API_URL")
AES_API_KEY = os.environ.get("AES_API_KEY")

if not AES_API_URL or not AES_API_KEY:
    sys.exit(
        "FATAL: AES_API_URL and AES_API_KEY must be set in the environment (see .env). "
        "Refusing to start with an empty fallback."
    )

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
app.config["JSON_SORT_KEYS"] = False

# NOTE: No longer using Flask session management
# Authentication is handled entirely by auth-service on Railway
# Clients store auth info locally and send Authorization header with requests

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("aes_logistics")


# ===== Register Auth Blueprint =====
# This automatically registers:
#   POST   /api/auth/login
#   POST   /api/auth/logout
#   GET    /api/auth/me
app.register_blueprint(auth_bp)


# ===== AES File Service Helper Functions =====
# Contract (AES File Service, Node/Express on the AES Windows server — see
# specs/007-integrations/spec.md):
#   POST {AES_API_URL}/api/upload        header X-API-Key
#   multipart: file, projectNumber (5-digit job number -> project folder),
#              fileType (key in the service's config/file-types.json),
#              filename (optional; saved name — an existing file is overwritten)
#   200 {success:true, fileName, destinationPath, projectName, ...}
#   400 {success:false, error|details}   401 invalid key   404 unknown route
# The service files into <project folder>\<fileTypes[fileType].destination>.
AES_FILE_TYPE_DELIVERY_PHOTO = "delivery_photo"
AES_FILE_TYPE_INTAKE_PHOTO = "intake_photo"
AES_FILE_TYPE_PACKING_SLIP = "packing_slip"


def aes_filename(prefix, job_number, label, original_filename):
    """Unique, filesystem-safe name: e.g. Delivery_Job12345_20260923-143022_ab12cd34_photo-1.jpg"""
    ext = os.path.splitext(original_filename or "")[1].lower() or ".jpg"
    safe = lambda v: re.sub(r"[^A-Za-z0-9\-]", "", str(v))
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return f"{safe(prefix)}_Job{safe(job_number)}_{stamp}_{os.urandom(4).hex()}_{safe(label)}{ext}"


def upload_to_aes(file_buffer, job_number, file_type, filename):
    """
    Upload one file to the AES File Service. Never raises.
    Returns {'success': True, 'file': <saved name>, 'path': <server path>}
         or {'success': False, 'error': '...'}
    """
    try:
        ext = os.path.splitext(filename)[1].lower()
        content_type = {".png": "image/png", ".pdf": "application/pdf"}.get(ext, "image/jpeg")
        response = requests.post(
            f"{AES_API_URL.rstrip('/')}/api/upload",
            files={"file": (filename, file_buffer, content_type)},
            data={"projectNumber": str(job_number).strip(), "fileType": file_type, "filename": filename},
            headers={"X-API-Key": AES_API_KEY},
            timeout=30,
        )
        try:
            body = response.json()
        except ValueError:
            body = {}
        if response.status_code == 200 and body.get("success"):
            log.info(f"✓ AES upload: {body.get('fileName')} -> {body.get('destinationPath')}")
            return {"success": True, "file": body.get("fileName"), "path": body.get("destinationPath")}
        err = body.get("error") or response.text[:300]
        if body.get("details"):
            err = f"{err}: {body['details']}"
        log.warning(f"AES upload failed (HTTP {response.status_code}) for {filename}: {err}")
        return {"success": False, "error": f"HTTP {response.status_code}: {err}"}
    except Exception as e:
        log.warning(f"AES upload error for {filename}: {e}")
        return {"success": False, "error": str(e)}


def upload_files_to_aes(job_number, items):
    """
    items: [(file_type, filename, bytes)]. Returns
    {'success': all ok, 'uploaded': [...ok results], 'failed': [...errors]}
    """
    results = {"success": True, "uploaded": [], "failed": []}
    for file_type, filename, buf in items:
        r = upload_to_aes(buf, job_number, file_type, filename)
        if r["success"]:
            results["uploaded"].append(r)
        else:
            results["success"] = False
            results["failed"].append({"file": filename, "error": r["error"]})
    log.info(f"AES upload summary for Job #{job_number}: {len(results['uploaded'])} ok, {len(results['failed'])} failed")
    return results


def upload_delivery_photos_to_aes(delivery_id, job_number, signature_buffer, photo_buffers,
                                  signature_filename="signature.png", photo_filenames=None):
    """Mirror a completed scheduled delivery's signature + photos to the job's project folder."""
    photo_filenames = photo_filenames or []
    items = [(AES_FILE_TYPE_DELIVERY_PHOTO,
              aes_filename("Delivery", job_number, "signature", signature_filename),
              signature_buffer)]
    for i, buf in enumerate(photo_buffers, start=1):
        orig = photo_filenames[i - 1] if i - 1 < len(photo_filenames) else "photo.jpg"
        items.append((AES_FILE_TYPE_DELIVERY_PHOTO, aes_filename("Delivery", job_number, f"photo-{i}", orig), buf))
    return upload_files_to_aes(job_number, items)


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


### --- Home and health check --- ###

@app.route("/")
def serve_driver_app():
    return send_from_directory(STATIC_DIR, "index.html")


@app.route("/pm")
def serve_pm_portal():
    return send_from_directory(PM_STATIC_DIR, "index.html")


@app.route("/<path:filename>")
def serve_static(filename):
    return send_from_directory(STATIC_DIR, filename)


@app.route("/pm/<path:filename>")
def serve_pm_static(filename):
    return send_from_directory(PM_STATIC_DIR, filename)


@app.route("/api/health")
def api_health():
    return jsonify({
        "status": "ok",
        "service": "AES Logistics Server",
        "timestamp": datetime.utcnow().isoformat()
    })


### --- Scheduled Delivery endpoints --- ###

@app.route("/api/schedule/calendar/settings", methods=["GET"])
@pm_or_admin_required
def api_schedule_calendar_settings_get():
    try:
        ics_url = scheduling.get_ics_url()
        return jsonify({"settings": {"ics_url": ics_url}})
    except Exception as e:
        log.error(f"Calendar settings retrieval failed: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/schedule/calendar/settings", methods=["POST"])
@pm_or_admin_required
def api_schedule_calendar_settings_post():
    data = request.get_json(silent=True) or {}
    ics_url = data.get("ics_url", "").strip()

    try:
        scheduling.set_ics_url(ics_url)
        return jsonify({"status": "ok", "ics_url": ics_url})
    except Exception as e:
        log.error(f"Calendar settings save failed: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/schedule/calendar/upcoming")
@pm_or_admin_required
def api_schedule_calendar_upcoming():
    try:
        events = scheduling.fetch_upcoming_events()
        return jsonify({"events": events})
    except Exception as e:
        log.error(f"Upcoming events retrieval failed: {e}")
        return jsonify({"error": str(e)}), 500

@app.route("/api/schedule", methods=["GET"])
@pm_or_admin_required
def api_schedule_list():
    try:
        deliveries = scheduling.list_deliveries()
        return jsonify({"deliveries": deliveries})
    except Exception as e:
        log.error(f"Schedule list failed: {e}")
        return jsonify({"error": str(e)}), 500

@app.route("/api/schedule", methods=["POST"])
@pm_or_admin_required
def api_schedule_create():
    data = request.get_json(silent=True) or {}

    required_fields = ["job_number", "receiver_name", "receiver_email", "receiver_phone", "site_address", "assigned_driver", "pm_email", "delivery_date"]
    missing = [f for f in required_fields if not data.get(f)]
    if missing:
        return jsonify({"error": f"missing fields: {', '.join(missing)}"}), 400

    try:
        # Generate a calendar_event_uid if not provided (for manual deliveries)
        calendar_event_uid = data.get("calendar_event_uid") or f"manual_{uuid.uuid4().hex[:8]}"
        
        delivery = scheduling.create_delivery(
            calendar_event_uid=calendar_event_uid,
            job_number=data["job_number"],
            receiver_name=data["receiver_name"],
            receiver_email=data["receiver_email"],
            receiver_phone=data["receiver_phone"],
            site_address=data["site_address"],
            assigned_driver=data["assigned_driver"],
            pm_email=data["pm_email"],
            delivery_date=data["delivery_date"],  # Added this
            customer_name=data.get("customer_name"),
            customer_po=data.get("customer_po"),
            job_name=data.get("job_name"),
            delivery_method=data.get("delivery_method"),
        )
        return jsonify({"status": "ok", "delivery": delivery})
    except Exception as e:
        log.error(f"Schedule creation failed: {e}")
        return jsonify({"error": str(e)}), 500
    

@app.route("/api/schedule/<delivery_id>/ticket", methods=["POST"])
@pm_or_admin_required
def api_schedule_ticket(delivery_id):
    delivery = scheduling.get_delivery(delivery_id)
    if not delivery:
        return jsonify({"error": f"no scheduled delivery found for id {delivery_id}"}), 404

    ticket_file = request.files.get("ticket")
    line_items = []
    
    if not ticket_file:
        if request.form.get("generate_ticket") != "true":
            return jsonify({"error": "missing ticket file"}), 400

        line_items_raw = request.form.get("line_items")
        try:
            line_items = json.loads(line_items_raw) if line_items_raw else []
        except json.JSONDecodeError:
            return jsonify({"error": "line_items must be valid JSON"}), 400

        ticket_bytes = ticket_render.render_ticket_image(
            job_number=delivery.get("job_number", ""),
            delivery_date=delivery.get("delivery_date", ""),
            receiver_name=delivery.get("receiver_name", ""),
            receiver_email=delivery.get("receiver_email", ""),
            site_address=delivery.get("site_address", ""),
            line_items=line_items,
            customer_name=delivery.get("customer_name", ""),
            customer_po=delivery.get("customer_po", ""),
            job_name=delivery.get("job_name", ""),
            delivery_method=delivery.get("delivery_method", ""),
            pm_name=delivery.get("pm_name", ""),
        )
    else:
        # File upload — use save_ticket_file
        record = scheduling.save_ticket_file(delivery_id, ticket_file)

        log.info(f"Ticket uploaded for delivery {delivery_id}")
        return jsonify({"status": "ok", "delivery": record})

    # Generate case continues here
    pm_name = delivery.get("pm_name", "")
    record = scheduling.save_generated_ticket(delivery_id, ticket_bytes, line_items, pm_name=pm_name)

    log.info(f"Ticket set for delivery {delivery_id}")
    return jsonify({"status": "ok", "delivery": record})


@app.route("/api/schedule/<delivery_id>/file/<n>")
def api_schedule_file(delivery_id, n):
    """
    Serve a file belonging to a scheduled delivery. `n` may be:
      - "ticket"                 -> the current ticket image
      - an int index             -> photo_filenames[n], then the signature at len(photos)
      - a stored filename        -> ticket_filename / photo / signature / packed signature
                                    (what driver_app + pm_portal actually send; WS-4)
    Only filenames recorded on the delivery are served — never arbitrary paths.
    No auth decorator (unchanged from HEAD): this URL is used as an <img src>,
    which can't carry the Bearer header. Tracked under spec 004.
    """
    delivery = scheduling.get_delivery(delivery_id)
    if not delivery:
        return jsonify({"error": f"no scheduled delivery found for id {delivery_id}"}), 404

    photo_filenames = delivery.get("photo_filenames") or []
    signature_filename = delivery.get("signature_filename")
    filename = None

    if n == "ticket":
        filename = delivery.get("ticket_filename")
    elif n.isdigit():
        n_int = int(n)
        if n_int < len(photo_filenames):
            filename = photo_filenames[n_int]
        elif n_int == len(photo_filenames) and signature_filename:
            filename = signature_filename
    else:
        allowed = set(photo_filenames) | {
            delivery.get("ticket_filename"),
            signature_filename,
            delivery.get("packed_signature_filename"),
        }
        allowed.discard(None)
        if n in allowed:
            filename = n

    if not filename:
        return jsonify({"error": "file not found"}), 404
    filepath = scheduling.delivery_file_path(delivery_id, filename)
    if not os.path.isfile(filepath):
        return jsonify({"error": "file not found"}), 404
    mimetype = "image/png" if filename.lower().endswith(".png") else "image/jpeg"
    return send_file(filepath, mimetype=mimetype, as_attachment=False)


@app.route("/api/schedule/<delivery_id>/generate_ticket", methods=["POST"])
@pm_or_admin_required
def api_schedule_generate_ticket(delivery_id):
    delivery = scheduling.get_delivery(delivery_id)
    if not delivery:
        return jsonify({"error": f"no scheduled delivery found for id {delivery_id}"}), 404

    data = request.get_json(silent=True) or {}
    line_items = data.get("line_items", [])

    try:
        ticket_bytes = ticket_render.render_ticket_image(
            job_number=delivery.get("job_number", ""),
            delivery_date=delivery.get("delivery_date", ""),
            receiver_name=delivery.get("receiver_name", ""),
            receiver_email=delivery.get("receiver_email", ""),
            site_address=delivery.get("site_address", ""),
            line_items=line_items,
            customer_name=delivery.get("customer_name", ""),
            customer_po=delivery.get("customer_po", ""),
            job_name=delivery.get("job_name", ""),
            delivery_method=delivery.get("delivery_method", ""),
            pm_name=delivery.get("pm_name", ""),
        )
        pm_name = delivery.get("pm_name", "")
        record = scheduling.save_generated_ticket(delivery_id, ticket_bytes, line_items, pm_name=pm_name)
        log.info(f"Ticket generated for delivery {delivery_id}")
        return jsonify({"status": "ok", "delivery": record})
    except Exception as e:
        log.error(f"Ticket generation failed: {e}")
        return jsonify({"error": str(e)}), 500

def _list_pms():
    """
    PMs + admins from auth-service, as [{name, email}] sorted by name.
    Falls back to PM emails already memoized in inventory's job->PM directory
    if auth-service is unreachable or refuses the caller (e.g. a warehouse user).
    """
    pms = []
    auth_header = request.headers.get("Authorization")
    if auth_header:
        users_response, status_code = call_auth_service(
            "/api/auth/admin/users", method="GET", auth_header=auth_header
        )
        if status_code == 200 and users_response and "users" in users_response:
            pms = [
                {"name": u.get("name") or u.get("email"), "email": u.get("email")}
                for u in users_response.get("users", [])
                if "pm" in (u.get("role") or "").lower() or "admin" in (u.get("role") or "").lower()
            ]
    if not pms:
        known = sorted(set(inventory._load_store()["job_pm_directory"].values()) - {None, ""})
        pms = [{"name": e, "email": e} for e in known]
    pms.sort(key=lambda x: (x["name"] or "").lower())
    return pms


@app.route("/api/schedule/pms")
@pm_or_admin_required
def api_schedule_pms():
    try:
        return jsonify({"pms": _list_pms()})
    except Exception as e:
        log.error(f"PM list failed: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/inventory/pms")
@login_required
def api_inventory_pms():
    """Driver-app PM picker (Incoming wizard needs_pm + Warehouse Send to PM)."""
    try:
        return jsonify({"pms": _list_pms()})
    except Exception as e:
        log.error(f"PM list failed: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/schedule/<delivery_id>/revise_ticket", methods=["POST"])
@pm_or_admin_required
def api_schedule_revise(delivery_id):
    delivery = scheduling.get_delivery(delivery_id)
    if not delivery:
        return jsonify({"error": f"no scheduled delivery found for id {delivery_id}"}), 404

    data = request.get_json(silent=True) or {}
    
    # If line_items are provided, regenerate the ticket with new line items
    line_items = data.get("line_items")
    if line_items is not None:
        try:
            ticket_bytes = ticket_render.render_ticket_image(
                job_number=delivery.get("job_number", ""),
                delivery_date=delivery.get("delivery_date", ""),
                receiver_name=delivery.get("receiver_name", ""),
                receiver_email=delivery.get("receiver_email", ""),
                site_address=delivery.get("site_address", ""),
                line_items=line_items,
                customer_name=delivery.get("customer_name", ""),
                customer_po=delivery.get("customer_po", ""),
                job_name=delivery.get("job_name", ""),
                delivery_method=delivery.get("delivery_method", ""),
                pm_name=delivery.get("pm_name", ""),
            )
            pm_name = delivery.get("pm_name", "")
            record = scheduling.save_generated_ticket(delivery_id, ticket_bytes, line_items, pm_name=pm_name)
            log.info(f"Ticket revised for delivery {delivery_id}")
            return jsonify({"status": "ok", "delivery": record})
        except Exception as e:
            log.error(f"Ticket revision failed: {e}")
            return jsonify({"error": str(e)}), 500
    
    # Otherwise, update delivery fields
    updates = {}
    if "job_number" in data:
        updates["job_number"] = data["job_number"]
    if "receiver_name" in data:
        updates["receiver_name"] = data["receiver_name"]
    if "receiver_email" in data:
        updates["receiver_email"] = data["receiver_email"]
    if "receiver_phone" in data:
        updates["receiver_phone"] = data["receiver_phone"]
    if "site_address" in data:
        updates["site_address"] = data["site_address"]
    if "customer_name" in data:
        updates["customer_name"] = data["customer_name"]
    if "customer_po" in data:
        updates["customer_po"] = data["customer_po"]
    if "job_name" in data:
        updates["job_name"] = data["job_name"]
    if "delivery_method" in data:
        updates["delivery_method"] = data["delivery_method"]

    if not updates:
        return jsonify({"error": "no fields to update"}), 400

    record = scheduling.revise_delivery(delivery_id, updates)
    revised_by = get_auth_header() or "unknown"
    log.info(f"Delivery {delivery_id} revised by {revised_by}: {updates}")
    return jsonify({"status": "ok", "delivery": record})


def _send_ticket_copy_to_pm(delivery_id):
    delivery = scheduling.get_delivery(delivery_id)
    if not delivery:
        return jsonify({"sent": False, "error": f"no scheduled delivery found for id {delivery_id}"}), 404

    data = request.get_json(silent=True) or {}
    recipient_pm_email = (data.get("pm_email") or "").strip()
    if not recipient_pm_email:
        return jsonify({"sent": False, "error": "missing pm_email"}), 400

    ticket_path = scheduling.ticket_file_path(delivery_id)
    if not ticket_path or not os.path.exists(ticket_path):
        return jsonify({"sent": False, "error": "ticket not yet set"}), 400

    sent, err = emailer.send_flag_email(
        to_addr=recipient_pm_email,
        subject=f"[AES Logistics] Delivery ticket copy — Job #{delivery['job_number']}",
        body_text=f"Forwarding ticket for Job #{delivery['job_number']}.",
        attachment_paths=[ticket_path],
    )
    if not sent:
        log.error(f"Failed to send ticket copy to {recipient_pm_email}: {err}")
        return jsonify({"status": "error", "sent": False, "error": err}), 500

    log.info(f"Ticket for delivery {delivery_id} sent to {recipient_pm_email} by {get_auth_header() or 'unknown'}")
    return jsonify({"status": "ok", "sent": True})


@app.route("/api/schedule/<delivery_id>/send_copy_to_pm", methods=["POST"])
@pm_or_admin_required
def api_schedule_send_copy_to_pm(delivery_id):
    """PM portal route."""
    return _send_ticket_copy_to_pm(delivery_id)


@app.route("/api/schedule/<delivery_id>/send_to_pm", methods=["POST"])
@login_required
def api_schedule_send_to_pm(delivery_id):
    """Driver-app (Warehouse / Ready to Pack) route — warehouse staff aren't PMs, so login only."""
    return _send_ticket_copy_to_pm(delivery_id)


@app.route("/api/schedule/warehouse/ready_to_pack")
@login_required
def api_schedule_ready_to_pack():
    return jsonify({"deliveries": scheduling.deliveries_ready_to_pack()})


@app.route("/api/schedule/<delivery_id>/pack", methods=["POST"])
@login_required
def api_schedule_pack(delivery_id):
    delivery = scheduling.get_delivery(delivery_id)
    if not delivery:
        return jsonify({"error": f"no scheduled delivery found for id {delivery_id}"}), 404

    packed_by = request.form.get("packed_by", "")
    signature_file = request.files.get("signature")

    if not packed_by or not signature_file:
        return jsonify({"error": "missing packed_by or signature"}), 400

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

    removed_count = inventory.mark_removed_by_job(delivery["job_number"])

    log.info(f"Delivery {delivery_id} packed by {packed_by}; {removed_count} inventory entr(ies) marked shipped for Job #{delivery['job_number']}")
    return jsonify({"status": "ok", "delivery": record, "inventory_entries_shipped": removed_count})

@app.route("/api/schedule/drivers")
@pm_or_admin_required
def api_schedule_drivers():
    try:
        # Get auth header from current request
        auth_header = request.headers.get("Authorization")
        if not auth_header:
            return jsonify({"error": "not authenticated"}), 401
        
        # Call auth-service with correct parameter order
        users_response, status_code = call_auth_service(
            "/api/auth/admin/users", 
            method="GET", 
            auth_header=auth_header
        )
        
        log.info(f"DEBUG: users_response = {users_response}, status = {status_code}")
        
        if status_code != 200 or not users_response or "users" not in users_response:
            return jsonify({"drivers": []})
        
        all_users = users_response.get("users", [])
        log.info(f"DEBUG: all_users = {all_users}")
        
        # Filter for drivers - check if "driver" is in the role
        drivers = [
            {"name": u.get("name")} 
            for u in all_users 
            if "driver" in u.get("role", "").lower()
        ]
        
        log.info(f"DEBUG: filtered drivers = {drivers}")
        drivers.sort(key=lambda x: x["name"])
        
        return jsonify({"drivers": drivers})
    except Exception as e:
        log.error(f"Driver list failed: {e}")
        return jsonify({"error": str(e)}), 500

@app.route("/api/schedule/driver/today")
@login_required
def api_schedule_driver_today():
    return jsonify({"deliveries": scheduling.deliveries_ready_for_driver()})


@app.route("/api/schedule/driver/mine")
@login_required
def api_schedule_driver_mine():
    # Get driver name from request body or query parameter
    driver_name = request.args.get("driver_name") or request.form.get("driver_name")
    if not driver_name:
        return jsonify({"error": "driver_name required"}), 400

    return jsonify({"deliveries": scheduling.deliveries_assigned_to(driver_name)})


@app.route("/api/schedule/<delivery_id>/start", methods=["POST"])
@login_required
def api_schedule_start(delivery_id):
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
    driver_email = get_auth_header()
    log.info(f"Delivery {delivery_id} started by driver {driver_email}. SMS sent: {sms_sent}. ETA: {eta}")

    return jsonify({
        "status": "ok",
        "delivery": record,
        "sms_sent": sms_sent,
        "sms_error": sms_error,
        "eta": eta,
    })


@app.route("/api/schedule/<delivery_id>/complete", methods=["POST"])
@login_required
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

    # ===== UPLOAD TO AES FILE SERVICE =====
    try:
        # Read file contents into memory
        sig_buffer = signature_file.read()
        signature_file.seek(0)  # Reset for local saving

        photo_buffers = []
        for photo_file in photo_files:
            photo_buffer = photo_file.read()
            photo_file.seek(0)  # Reset for local saving
            photo_buffers.append(photo_buffer)

        # Upload to AES
        aes_result = upload_delivery_photos_to_aes(
            delivery_id=delivery_id,
            job_number=delivery["job_number"],
            signature_buffer=sig_buffer,
            photo_buffers=photo_buffers,
            signature_filename=signature_file.filename or "signature.png",
            photo_filenames=[p.filename for p in photo_files],
        )
    except Exception as e:
        log.error(f"Error uploading to AES: {str(e)}")
        aes_result = {"success": False, "uploaded": [], "failed": [{"error": str(e)}]}
        # Continue anyway - local saving will still work

    # ===== CONTINUE WITH LOCAL SAVING =====
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
    return jsonify({
        "status": "ok",
        "delivery": record,
        "file_service": {"success": aes_result["success"], "uploaded": len(aes_result["uploaded"]), "failed": aes_result["failed"]},
    })


### --- Inventory (location tracking + Excel report) --- ###

@app.route("/api/inventory/locations")
@login_required
def api_inventory_locations():
    return jsonify({"locations": inventory.LOCATIONS})


@app.route("/api/inventory")
@login_required
def api_inventory_list():
    return jsonify({"entries": inventory.list_entries()})


@app.route("/api/inventory/<entry_id>/remove", methods=["POST"])
@pm_or_admin_required
def api_inventory_remove(entry_id):
    entry = inventory.mark_removed(entry_id)
    if not entry:
        return jsonify({"error": f"no inventory entry found for id {entry_id}"}), 404
    return jsonify({"status": "ok", "entry": entry})


@app.route("/api/inventory/export")
@pm_or_admin_required
def api_inventory_export():
    report_bytes = inventory_report.build_report()
    filename = f"AES_Inventory_{datetime.now().strftime('%Y-%m-%d')}.xlsx"
    return send_file(
        io.BytesIO(report_bytes),
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name=filename,
    )


### --- Incoming Inventory (packing slips) endpoints --- ###

@app.route("/api/incoming/scan", methods=["POST"])
@login_required
def api_incoming_scan():
    slip_file = request.files.get("slip")
    if not slip_file:
        return jsonify({"error": "missing 'slip' file"}), 400

    slip_bytes = slip_file.read()
    slip_path = os.path.join(CFG["incoming_staging_dir"], f"{uuid.uuid4()}.jpg")
    os.makedirs(os.path.dirname(slip_path), exist_ok=True)
    with open(slip_path, "wb") as f:
        f.write(slip_bytes)

    job_pattern = CFG.get("job_number_pattern", r"job\s*#?\s*:?\s*(?P<job>\d{3,8})")
    po_pattern = CFG.get("po_number_pattern", r"p\.o\.\s*#?\s*:?\s*(?P<po>[A-Za-z0-9\-]{3,20})")

    job_number = extract_job_number(slip_path, job_pattern)
    po_number = extract_po_number(slip_path, po_pattern)

    return jsonify({
        "status": "ok",
        "slip_id": os.path.basename(slip_path),
        "job_number": job_number,
        "po_number": po_number,
    })


@app.route("/api/incoming/confirm", methods=["POST"])
@login_required
def api_incoming_confirm():
    data = request.get_json(silent=True) or {}
    slip_id = data.get("slip_id", "").strip()
    job_number = data.get("job_number", "").strip()
    po_number = data.get("po_number", "").strip()

    if not slip_id or not job_number:
        return jsonify({"error": "missing slip_id or job_number"}), 400

    slip_path = os.path.join(CFG["incoming_staging_dir"], slip_id)
    if not os.path.exists(slip_path):
        return jsonify({"error": "slip not found"}), 404

    dest_dir = _slip_job_dir(job_number)
    final_path = unique_destination(dest_dir, f"packing_slip_{slip_id}")
    os.makedirs(os.path.dirname(final_path), exist_ok=True)
    shutil.move(slip_path, final_path)

    # Log who confirmed
    confirmed_by = get_auth_header() or "unknown"
    record = inventory.add_entry(
        job_number=job_number,
        po_number=po_number,
        confirmed_by=confirmed_by,
        slip_photo_filenames=[os.path.basename(final_path)],
        pm_email=inventory.get_pm_for_job(job_number),
    )
    log.info(f"Packing slip {slip_id} filed for Job #{job_number} by {confirmed_by}")

    return jsonify({"status": "ok", "entry": record})

@app.route("/api/schedule/<delivery_id>", methods=["DELETE"])
@pm_or_admin_required
def api_schedule_delete(delivery_id):
    try:
        delivery = scheduling.delete_delivery(delivery_id)
        if not delivery:
            return jsonify({"error": f"no scheduled delivery found for id {delivery_id}"}), 404
        
        deleted_by = get_auth_header() or "unknown"
        log.info(f"Delivery {delivery_id} deleted by {deleted_by}")
        return jsonify({"status": "ok", "message": f"Delivery {delivery_id} deleted"})
    except Exception as e:
        log.error(f"Delivery deletion failed: {e}")
        return jsonify({"error": str(e)}), 500
    
@app.route("/api/incoming/flag", methods=["POST"])
@login_required
def api_incoming_flag():
    """
    Flag a packing slip that has no/bad job number. Accepts either the
    wizard body {session_id, reason, note, staff} (flags every scanned page)
    or the legacy single-shot body {slip_id, reason}.
    """
    data = request.get_json(silent=True) or {}
    session_id = (data.get("session_id") or "").strip()
    slip_id = (data.get("slip_id") or "").strip()
    reason = (data.get("reason") or "no job number").strip()
    note = (data.get("note") or "").strip()
    flagged_by = (data.get("staff") or "").strip() or get_auth_header() or "unknown"

    flagged_dir = os.path.join(CFG["dest_dir"], CFG.get("flagged_slips_folder", "flagged_packing_slips"))
    os.makedirs(flagged_dir, exist_ok=True)
    moved = []

    if session_id:
        sess = _load_incoming_session(session_id)
        if not sess:
            return jsonify({"error": "incoming session not found"}), 404
        sdir = _incoming_session_dir(session_id)
        for name in sess["pages"]:
            src = os.path.join(sdir, name)
            if os.path.exists(src):
                dst = unique_destination(flagged_dir, f"{session_id[:8]}_{name}")
                shutil.move(src, dst)
                moved.append(dst)
        shutil.rmtree(sdir, ignore_errors=True)
    elif slip_id:
        if os.path.basename(slip_id) != slip_id:
            return jsonify({"error": "invalid slip_id"}), 400
        slip_path = os.path.join(CFG["incoming_staging_dir"], slip_id)
        if not os.path.exists(slip_path):
            return jsonify({"error": "slip not found"}), 404
        dst = unique_destination(flagged_dir, slip_id)
        shutil.move(slip_path, dst)
        moved.append(dst)
    else:
        return jsonify({"error": "missing session_id or slip_id"}), 400

    body = f"A packing slip could not be processed.\nReason: {reason}\nFlagged by: {flagged_by}"
    if note:
        body += f"\nNote: {note}"
    sent, err = emailer.send_flag_email(
        to_addr=CFG.get("flag_alert_email_to", "PMteam@aes-energy.com"),
        subject="[AES Logistics] Flagged packing slip — could not read job number",
        body_text=body,
        attachment_paths=moved,
    )
    log.info(f"Packing slip ({session_id or slip_id}) flagged by {flagged_by}; {len(moved)} page(s). Email sent: {sent}")
    return jsonify({"status": "ok", "email_sent": sent, "email_error": err})


### --- Ad-hoc delivery sync (driver app "Sync Now") — spec 001 WS-3 --- ###

_ADHOC_ID_RE = re.compile(r"^[A-Za-z0-9\-_]{1,64}$")


@app.route("/api/upload", methods=["POST"])
@login_required
def api_upload():
    """
    multipart: metadata (JSON {delivery_id, driver, completed_at, photos:[{filename,type,captured_at}]})
               + one file part per photo, keyed by its filename.
    OCRs the job number off the ticket photo(s) and files the delivery into
    <dest_dir>/Job_<n>/ (or <dest_dir>/needs_review_no_job_number/<delivery_id>/).
    Idempotent per delivery_id: a retried sync overwrites the same files.
    Mirrors to the AES File Service (delivery_photo) when a job number was read.
    """
    try:
        meta = json.loads(request.form.get("metadata") or "{}")
    except json.JSONDecodeError:
        return jsonify({"error": "metadata must be JSON"}), 400
    delivery_id = str(meta.get("delivery_id") or "").strip()
    if not _ADHOC_ID_RE.match(delivery_id):
        return jsonify({"error": "missing or invalid delivery_id"}), 400

    photos = []
    for p in meta.get("photos") or []:
        name = os.path.basename(str((p or {}).get("filename") or ""))
        f = request.files.get(name) if name else None
        if not f:
            continue
        photos.append({"filename": name, "type": (p.get("type") or "other"), "captured_at": p.get("captured_at"), "file": f})
    if not photos:
        return jsonify({"error": "no photos received"}), 400

    # Save to a per-delivery staging dir first so OCR can read from disk.
    stage = os.path.join(CFG["incoming_dir"], "_adhoc", delivery_id)
    os.makedirs(stage, exist_ok=True)
    for p in photos:
        p["file"].save(os.path.join(stage, p["filename"]))

    job_number = None
    job_pattern = CFG.get("job_number_pattern", r"job\s*#?\s*:?\s*(?P<job>\d{3,8})")
    for p in [p for p in photos if p["type"] == "ticket"]:
        job_number = extract_job_number(os.path.join(stage, p["filename"]), job_pattern)
        if job_number:
            break

    if job_number:
        # Photo filenames already start with the delivery id, so a shared Job_<n>/ is fine.
        dest = os.path.join(CFG["dest_dir"], f"Job_{re.sub(r'[^A-Za-z0-9-_]', '_', job_number)}")
    else:
        dest = os.path.join(CFG["dest_dir"], CFG["review_folder"], delivery_id)
    os.makedirs(dest, exist_ok=True)

    filed = []
    for p in photos:
        final = os.path.join(dest, p["filename"])
        shutil.move(os.path.join(stage, p["filename"]), final)  # overwrite on retry
        filed.append(final)

    has_pallet = any(p["type"] == "pallet" for p in photos)
    flag_name = f"{delivery_id}_{CFG['incomplete_flag_filename']}"
    if not has_pallet:
        with open(os.path.join(dest, flag_name), "w") as fh:
            fh.write(f"Delivery {delivery_id} synced without a pallet/box photo.\n")

    driver = str(meta.get("driver") or "") or get_auth_header() or "unknown"
    with open(os.path.join(dest, f"{delivery_id}_metadata.json"), "w") as fh:
        json.dump({
            "delivery_id": delivery_id,
            "job_number": job_number,
            "driver": driver,
            "completed_at": meta.get("completed_at"),
            "synced_at": datetime.now().isoformat(),
            "photos": [{k: p[k] for k in ("filename", "type", "captured_at")} for p in photos],
            "incomplete_missing_pallet_photo": not has_pallet,
        }, fh, indent=2)
    shutil.rmtree(stage, ignore_errors=True)

    if job_number:
        counters = {}
        items = []
        for p, path in zip(photos, filed):
            counters[p["type"]] = counters.get(p["type"], 0) + 1
            with open(path, "rb") as fh:
                # Deterministic name (delivery id, not a timestamp) so a retried
                # sync overwrites instead of duplicating in the project folder.
                ext = os.path.splitext(p["filename"])[1].lower() or ".jpg"
                safe_type = re.sub(r"[^A-Za-z0-9-]", "", p["type"])
                name = f"AdHoc_Job{re.sub(r'[^A-Za-z0-9-]', '', job_number)}_{delivery_id}_{safe_type}-{counters[p['type']]}{ext}"
                items.append((AES_FILE_TYPE_DELIVERY_PHOTO, name, fh.read()))
        aes_result = upload_files_to_aes(job_number, items)
    else:
        aes_result = {"success": False, "uploaded": [], "failed": [{"error": "no job number read from ticket — filed for review, not mirrored"}]}

    log.info(f"Ad-hoc delivery {delivery_id} by {driver}: {len(photos)} photo(s) -> {dest}")
    return jsonify({
        "status": "ok",
        "delivery_id": delivery_id,
        "job_number": job_number,
        "needs_review": job_number is None,
        "incomplete": not has_pallet,
        "file_service": {"success": aes_result["success"], "uploaded": len(aes_result["uploaded"]), "failed": aes_result["failed"]},
    })


### --- Incoming Inventory wizard (session-based; spec 005 / contracts/api.md) --- ###
#
# The driver app's Incoming Inventory flow is a multi-step wizard:
#   scan_page (xN) -> confirm_job -> pallet_photo (xN) -> finalize   (or -> flag)
# Session state lives on disk under <incoming_staging_dir>/<session_id>/ so it
# survives across gunicorn workers (in-memory state would not).

_SESSION_ID_RE = re.compile(r"^[0-9a-f]{32}$")


def _incoming_session_dir(session_id):
    return os.path.join(CFG["incoming_staging_dir"], session_id)


def _load_incoming_session(session_id):
    if not session_id or not _SESSION_ID_RE.match(session_id):
        return None
    path = os.path.join(_incoming_session_dir(session_id), "session.json")
    if not os.path.isfile(path):
        return None
    with open(path, "r") as f:
        return json.load(f)


def _save_incoming_session(sess):
    sdir = _incoming_session_dir(sess["session_id"])
    os.makedirs(sdir, exist_ok=True)
    tmp = os.path.join(sdir, "session.json.tmp")
    with open(tmp, "w") as f:
        json.dump(sess, f, indent=2)
    os.replace(tmp, os.path.join(sdir, "session.json"))


def _slip_job_dir(job_number):
    safe_job = re.sub(r"[^A-Za-z0-9\-_]", "_", job_number)
    return os.path.join(CFG["dest_dir"], CFG["incoming_slip_subfolder"], f"Job_{safe_job}")


def _uploaded_photo(field="photo"):
    return request.files.get(field) or request.files.get("slip")


@app.route("/api/incoming/scan_page", methods=["POST"])
@login_required
def api_incoming_scan_page():
    """
    multipart: photo (or slip), session_id? -> {session_id, page_count, job_number_guess, po_number_guess}
    First call (no session_id) opens a session. Guesses are sticky: the first
    page that yields a job/PO number wins.
    """
    photo = _uploaded_photo()
    if not photo:
        return jsonify({"error": "missing 'photo' file"}), 400

    session_id = (request.form.get("session_id") or "").strip()
    sess = _load_incoming_session(session_id) if session_id else None
    if session_id and not sess:
        return jsonify({"error": "incoming session not found"}), 404
    if not sess:
        sess = {
            "session_id": uuid.uuid4().hex,
            "created_at": datetime.now().isoformat(),
            "created_by": get_auth_header() or "unknown",
            "status": "scanning",
            "pages": [],
            "pallet_photos": [],
            "job_number_guess": None,
            "po_number_guess": None,
        }
    if sess["status"] not in ("scanning", "confirmed"):
        return jsonify({"error": f"session is {sess['status']}"}), 409

    sdir = _incoming_session_dir(sess["session_id"])
    os.makedirs(sdir, exist_ok=True)
    page_name = f"page_{len(sess['pages']) + 1}.jpg"
    page_path = os.path.join(sdir, page_name)
    photo.save(page_path)
    sess["pages"].append(page_name)

    if not sess["job_number_guess"]:
        sess["job_number_guess"] = extract_job_number(page_path, CFG["job_number_pattern"]) if CFG.get("job_number_pattern") else None
    if not sess["po_number_guess"]:
        sess["po_number_guess"] = extract_po_number(page_path, CFG["po_number_pattern"])
    _save_incoming_session(sess)

    return jsonify({
        "status": "ok",
        "session_id": sess["session_id"],
        "page_count": len(sess["pages"]),
        "job_number_guess": sess["job_number_guess"],
        "po_number_guess": sess["po_number_guess"],
    })


@app.route("/api/incoming/confirm_job", methods=["POST"])
@login_required
def api_incoming_confirm_job():
    """
    JSON {session_id, job_number, po_number?, staff?, pm_email?}
    Resolves the owning PM from pm_email or the job->PM directory; if neither,
    returns 400 {"error":"needs_pm"} so the app shows its PM picker.
    """
    data = request.get_json(silent=True) or {}
    sess = _load_incoming_session((data.get("session_id") or "").strip())
    if not sess:
        return jsonify({"error": "incoming session not found"}), 404
    if not sess["pages"]:
        return jsonify({"error": "scan at least one page first"}), 400
    if sess["status"] == "finalized":
        return jsonify({"error": "session already finalized"}), 409

    job_number = (data.get("job_number") or "").strip()
    if not job_number:
        return jsonify({"error": "missing job_number"}), 400
    po_number = (data.get("po_number") or "").strip()

    pm_email = (data.get("pm_email") or "").strip()
    if pm_email:
        inventory.set_pm_for_job(job_number, pm_email)
    else:
        pm_email = inventory.get_pm_for_job(job_number)
    if not pm_email:
        return jsonify({"error": "needs_pm"}), 400

    sess.update({
        "status": "confirmed",
        "job_number": job_number,
        "po_number": po_number,
        "pm_email": pm_email,
        "staff": (data.get("staff") or "").strip() or get_auth_header() or "unknown",
        "confirmed_at": datetime.now().isoformat(),
    })
    _save_incoming_session(sess)
    return jsonify({"status": "ok", "session_id": sess["session_id"], "pm_email": pm_email})


@app.route("/api/incoming/pallet_photo", methods=["POST"])
@login_required
def api_incoming_pallet_photo():
    """multipart: session_id, photo -> {pallet_photo_count}"""
    sess = _load_incoming_session((request.form.get("session_id") or "").strip())
    if not sess:
        return jsonify({"error": "incoming session not found"}), 404
    if sess["status"] != "confirmed":
        return jsonify({"error": "confirm the job number before adding pallet photos"}), 409
    photo = _uploaded_photo()
    if not photo:
        return jsonify({"error": "missing 'photo' file"}), 400

    name = f"pallet_{len(sess['pallet_photos']) + 1}.jpg"
    photo.save(os.path.join(_incoming_session_dir(sess["session_id"]), name))
    sess["pallet_photos"].append(name)
    _save_incoming_session(sess)
    return jsonify({"status": "ok", "pallet_photo_count": len(sess["pallet_photos"])})


@app.route("/api/incoming/finalize", methods=["POST"])
@login_required
def api_incoming_finalize():
    """
    JSON {session_id, pallet_count, locations:[{location,count}], comment?}
    -> {entry, qr_pdf_url, email_sent}
    Server-side gates (previously client-only): one photo per pallet, every
    location is one of inventory.LOCATIONS, and split counts sum to pallet_count.
    """
    data = request.get_json(silent=True) or {}
    sess = _load_incoming_session((data.get("session_id") or "").strip())
    if not sess:
        return jsonify({"error": "incoming session not found"}), 404
    if sess["status"] != "confirmed":
        return jsonify({"error": "confirm the job number before finalizing"}), 409

    try:
        pallet_count = int(data.get("pallet_count"))
    except (TypeError, ValueError):
        return jsonify({"error": "pallet_count must be an integer"}), 400
    if pallet_count < 1:
        return jsonify({"error": "pallet_count must be at least 1"}), 400
    if len(sess["pallet_photos"]) < pallet_count:
        return jsonify({"error": f"expected {pallet_count} pallet photo(s), got {len(sess['pallet_photos'])}"}), 400

    locations = []
    for row in data.get("locations") or []:
        loc = (row or {}).get("location")
        try:
            count = int((row or {}).get("count"))
        except (TypeError, ValueError):
            return jsonify({"error": "each location needs an integer count"}), 400
        if loc not in inventory.LOCATIONS:
            return jsonify({"error": f"unknown location: {loc}"}), 400
        if count < 1:
            return jsonify({"error": "location counts must be at least 1"}), 400
        locations.append({"location": loc, "count": count})
    if not locations:
        return jsonify({"error": "at least one location is required"}), 400
    if sum(l["count"] for l in locations) != pallet_count:
        return jsonify({"error": "location counts must add up to the pallet count"}), 400

    # File slip pages + pallet photos under Incoming_Packing_Slips/Job_<n>/
    job_number = sess["job_number"]
    sdir = _incoming_session_dir(sess["session_id"])
    job_dir = _slip_job_dir(job_number)
    os.makedirs(job_dir, exist_ok=True)
    prefix = sess["session_id"][:8]

    def _file(names):
        out = []
        for name in names:
            src = os.path.join(sdir, name)
            if os.path.exists(src):
                dst = unique_destination(job_dir, f"{prefix}_{name}")
                shutil.move(src, dst)
                out.append(os.path.basename(dst))
        return out

    slip_files = _file(sess["pages"])
    pallet_files = _file(sess["pallet_photos"])

    entry = inventory.add_entry(
        job_number=job_number,
        po_number=sess.get("po_number", ""),
        confirmed_by=sess.get("staff") or "unknown",
        slip_photo_filenames=slip_files,
        pm_email=sess["pm_email"],
        pallet_count=pallet_count,
        pallet_photo_filenames=pallet_files,
        locations=locations,
        comment=(data.get("comment") or "").strip(),
    )

    qr_filename = f"{prefix}_receiving_qr.pdf"
    qr_path = os.path.join(job_dir, qr_filename)
    try:
        base_url = os.environ.get("PUBLIC_BASE_URL") or request.host_url
        pdf_bytes = qr_ticket.build_qr_pdf(entry["id"], job_number, entry["po_number"], base_url, locations, pallet_count)
        with open(qr_path, "wb") as f:
            f.write(pdf_bytes)
        entry = inventory.set_qr_pdf_filename(entry["id"], qr_filename)
    except Exception as e:
        log.error(f"QR PDF build failed for entry {entry['id']}: {e}")
        qr_path = None

    loc_text = ", ".join(f"{l['location']} ({l['count']})" for l in locations)
    body = (
        f"New shipment received for Job #{job_number}.\n"
        f"PO #: {entry['po_number'] or '(none)'}\n"
        f"Pallets: {pallet_count}\n"
        f"Location(s): {loc_text}\n"
        f"Received by: {entry['confirmed_by']}\n"
    )
    if entry.get("comment"):
        body += f"Comment: {entry['comment']}\n"
    attachments = [os.path.join(job_dir, n) for n in slip_files] + ([qr_path] if qr_path else [])
    sent, err = emailer.send_flag_email(
        to_addr=sess["pm_email"],
        subject=f"[AES Logistics] Shipment received — Job #{job_number}",
        body_text=body,
        attachment_paths=attachments,
    )

    # Mirror to the AES File Service (non-fatal): slip pages -> packing_slip,
    # pallet photos -> intake_photo, in the job's project folder.
    aes_items = []
    for i, name in enumerate(slip_files, start=1):
        with open(os.path.join(job_dir, name), "rb") as f:
            aes_items.append((AES_FILE_TYPE_PACKING_SLIP, aes_filename("PackingSlip", job_number, f"page-{i}", name), f.read()))
    for i, name in enumerate(pallet_files, start=1):
        with open(os.path.join(job_dir, name), "rb") as f:
            aes_items.append((AES_FILE_TYPE_INTAKE_PHOTO, aes_filename("Intake", job_number, f"pallet-{i}", name), f.read()))
    aes_result = upload_files_to_aes(job_number, aes_items)

    shutil.rmtree(sdir, ignore_errors=True)
    log.info(f"Incoming shipment finalized: entry {entry['id']} Job #{job_number}, {pallet_count} pallet(s). PM email sent: {sent}")
    return jsonify({
        "status": "ok",
        "entry": entry,
        "qr_pdf_url": f"/api/inventory/{entry['id']}/qr.pdf" if entry.get("qr_pdf_filename") else None,
        "email_sent": sent,
        "email_error": err,
        "file_service": {"success": aes_result["success"], "uploaded": len(aes_result["uploaded"]), "failed": aes_result["failed"]},
    })


@app.route("/api/inventory/<entry_id>/qr.pdf")
@login_required
def api_inventory_qr_pdf(entry_id):
    entry = inventory.get_entry(entry_id)
    if not entry or not entry.get("qr_pdf_filename"):
        return jsonify({"error": "no QR label for this entry"}), 404
    path = os.path.join(_slip_job_dir(entry["job_number"]), entry["qr_pdf_filename"])
    if not os.path.isfile(path):
        return jsonify({"error": "QR label file missing"}), 404
    return send_file(path, mimetype="application/pdf", as_attachment=False)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)