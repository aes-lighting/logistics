#!/usr/bin/env python3
"""
AES Logistics - server app

Serves the driver PWA (static files) and receives delivery photo uploads
from drivers' phones. Because the app itself tags each photo as "ticket" or
"pallet" and groups them by delivery at capture time, the server doesn't have
to guess anything the way the old folder-watching script did — it just reads
the job number off the ticket via OCR and files the whole delivery.

NOW INTEGRATED: Photos are also automatically uploaded to the AES File Service
at http://71.172.107.128:3001 for centralized storage.

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
    GET  /api/schedule/<id>/file/<n>       -> serve a ticket/signature/photo file (any logged in role)
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
from functools import wraps

from dotenv import load_dotenv
from flask import Flask, request, jsonify, send_from_directory, session, send_file
import requests

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

# ===== Auth Service Configuration =====
AUTH_SERVICE_URL = os.environ.get("AUTH_SERVICE_URL", "http://localhost:5000")

# ===== AES File Service Configuration =====
AES_API_URL = os.environ.get("AES_API_URL", "http://71.172.107.128:3001")
AES_API_KEY = os.environ.get("AES_API_KEY", "yvgDtDvqWY2L8A5gb8k4btePZRW20b9m3ur0vgpinZDoF1pcqgjwmhofS8Z0Yxfb")

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
    SESSION_COOKIE_SECURE=True,
    PERMANENT_SESSION_LIFETIME=60 * 60 * 24 * 30,  # 30 days
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("aes_logistics")


# ===== AES File Service Helper Functions =====
def generate_aes_filename(directory, shipment_id, original_filename):
    """
    Generate filename in AES format: DIRECTORY_SHIPMENT_TIMESTAMP_HASH.ext
    Example: DELIVERY_SHIP-12345_20260828T143022_abc12345.jpg
    """
    # Get file extension
    name_parts = original_filename.rsplit('.', 1)
    if len(name_parts) < 2:
        ext = ''
    else:
        ext = '.' + name_parts[1].lower()
    
    # Generate timestamp (YYYYMMDDTHHmmss format)
    timestamp = datetime.utcnow().strftime("%Y%m%dT%H%M%S")
    
    # Generate short hash (8 characters)
    random_bytes = os.urandom(4)
    hash_suffix = random_bytes.hex()[:8]
    
    # Format: DIRECTORY_SHIPMENT_TIMESTAMP_HASH.ext
    filename = f"{directory}_{shipment_id}_{timestamp}_{hash_suffix}{ext}"
    return filename


def upload_to_aes(file_buffer, directory, shipment_id, original_filename, metadata=None):
    """
    Upload a photo to the AES File Service.
    
    Returns:
        {'success': True, 'file': '...', 'url': '...'} on success
        {'success': False, 'error': '...'} on failure
    """
    try:
        # Generate the AES-formatted filename
        aes_filename = generate_aes_filename(directory, shipment_id, original_filename)
        
        # Prepare multipart form data
        files = {'file': (aes_filename, file_buffer, 'image/jpeg')}
        
        # ✅ CORRECTED PARAMETERS per API spec:
        # - logisticsId: REQUIRED (shipment ID)
        # - directoryPath: REQUIRED (which directory to save to)
        data = {
            'logisticsId': shipment_id,     # REQUIRED - tells API the job/shipment ID
            'directoryPath': directory       # REQUIRED - tells API which directory (INTAKE, DELIVERY, etc)
        }
        
        if metadata:
            data['metadata'] = json.dumps(metadata)
        
        headers = {'X-API-Key': AES_API_KEY}
        
        # ✅ CORRECTED ENDPOINT: /api/files/upload (not /api/upload)
        response = requests.post(
            f"{AES_API_URL}/api/files/upload",  # FIXED: Added /files
            files=files,
            data=data,
            headers=headers,
            timeout=30
        )
        
        if response.status_code == 200:
            result = response.json()
            # Response structure: {"success": true, "data": {fileId, fileName, filePath, size, uploadedAt}}
            file_data = result.get('data', {})
            log.info(f"✓ AES upload success: {file_data.get('fileName')}")
            return {
                'success': True,
                'file': file_data.get('fileName'),
                'fileId': file_data.get('fileId'),
                'size': file_data.get('size'),
                'url': f"{AES_API_URL}/api/files/{file_data.get('fileId')}"
            }
        else:
            log.warning(f"AES upload failed (HTTP {response.status_code}): {response.text}")
            return {'success': False, 'error': f"HTTP {response.status_code}: {response.text}"}
    
    except Exception as e:
        log.warning(f"AES upload error: {str(e)}")
        return {'success': False, 'error': str(e)}


def upload_delivery_photos_to_aes(delivery_id, job_number, signature_buffer, photo_buffers):
    """
    Upload all photos from a completed delivery to AES.
    
    Returns:
        {'success': True/False, 'uploaded': [...], 'failed': [...]}
    """
    results = {
        'success': True,
        'uploaded': [],
        'failed': []
    }
    
    # Construct shipment ID for AES (used across all uploads for this delivery)
    shipment_id = f"SHIP-{delivery_id}"
    
    # Upload signature
    sig_result = upload_to_aes(
        signature_buffer,
        'DELIVERY',
        shipment_id,
        'signature.jpg',
        {'type': 'signature', 'job_number': job_number}
    )
    results['uploaded'].append(sig_result)
    if not sig_result['success']:
        results['success'] = False
        log.warning(f"Signature upload failed for delivery {delivery_id}: {sig_result['error']}")
    
    # Upload delivery photos
    for i, photo_buffer in enumerate(photo_buffers):
        photo_result = upload_to_aes(
            photo_buffer,
            'DELIVERY',
            shipment_id,
            f"delivery-photo-{i+1}.jpg",
            {'type': 'delivery_photo', 'photo_number': i+1, 'job_number': job_number}
        )
        results['uploaded'].append(photo_result)
        if not photo_result['success']:
            results['success'] = False
            log.warning(f"Photo {i+1} upload failed for delivery {delivery_id}: {photo_result['error']}")
    
    log.info(f"AES upload summary for delivery {delivery_id}: {len([u for u in results['uploaded'] if u['success']])} succeeded, {len([u for u in results['uploaded'] if not u['success']])} failed")
    return results


# ===== Auth Decorators =====
def login_required(f):
    """Decorator to require login - checks local session."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "user_id" not in session:
            return jsonify({"error": "not logged in"}), 401
        return f(*args, **kwargs)
    return decorated_function


def admin_required(f):
    """Decorator to require admin role."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "user_id" not in session:
            return jsonify({"error": "not logged in"}), 401
        if session.get("role") != "admin":
            return jsonify({"error": "admin access required"}), 403
        return f(*args, **kwargs)
    return decorated_function


def pm_or_admin_required(f):
    """Decorator to require PM or admin role."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "user_id" not in session:
            return jsonify({"error": "not logged in"}), 401
        if session.get("role") not in ("pm", "admin"):
            return jsonify({"error": "pm or admin access required"}), 403
        return f(*args, **kwargs)
    return decorated_function


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


@app.route("/api/health")
def api_health():
    return jsonify({
        "status": "ok",
        "service": "AES Logistics Server",
        "timestamp": datetime.utcnow().isoformat()
    })


### --- Auth endpoints --- ###

@app.route("/api/auth/driver_login", methods=["POST"])
def api_auth_driver_login():
    data = request.get_json(silent=True) or {}
    name = data.get("name", "").strip()
    code = data.get("code", "").strip()

    if not name or not code:
        return jsonify({"error": "missing name or code"}), 400

    session.permanent = True
    session["user_id"] = f"driver_{name}"
    session["name"] = name
    session["role"] = "driver"
    return jsonify({"status": "ok", "name": name})


@app.route("/api/auth/admin_login", methods=["POST"])
def api_auth_admin_login():
    data = request.get_json(silent=True) or {}
    email = data.get("email", "").strip()
    password = data.get("password", "").strip()

    admin_email = os.environ.get("ADMIN_EMAIL")
    admin_password = os.environ.get("ADMIN_PASSWORD", "admin")

    if not email or not password or email != admin_email or password != admin_password:
        return jsonify({"error": "invalid credentials"}), 401

    session.permanent = True
    session["user_id"] = email
    session["email"] = email
    session["role"] = "admin"
    return jsonify({"status": "ok", "email": email})


@app.route("/api/auth/pm_login", methods=["POST"])
def api_auth_pm_login():
    data = request.get_json(silent=True) or {}
    email = data.get("email", "").strip()
    password = data.get("password", "").strip()

    if not email or not password:
        return jsonify({"error": "missing email or password"}), 400

    pm_record = None
    try:
        from scheduling import get_pm_by_email
        pm_record = get_pm_by_email(email)
    except Exception as e:
        log.warning(f"PM lookup failed: {e}")

    if not pm_record or pm_record.get("password") != password:
        return jsonify({"error": "invalid credentials"}), 401

    session.permanent = True
    session["user_id"] = email
    session["email"] = email
    session["name"] = pm_record.get("name", email)
    session["role"] = "pm"
    return jsonify({"status": "ok", "email": email, "name": session["name"]})


@app.route("/api/auth/logout", methods=["POST"])
def api_auth_logout():
    session.clear()
    return jsonify({"status": "ok"})


@app.route("/api/auth/me")
def api_auth_me():
    if "user_id" not in session:
        return jsonify({"error": "not logged in"}), 401
    return jsonify({
        "user_id": session.get("user_id"),
        "name": session.get("name"),
        "email": session.get("email"),
        "role": session.get("role"),
    })


@app.route("/api/auth/admin/reset_driver_code", methods=["POST"])
@admin_required
def api_auth_admin_reset_driver_code():
    data = request.get_json(silent=True) or {}
    name = data.get("name", "").strip()
    if not name:
        return jsonify({"error": "missing driver name"}), 400
    return jsonify({"status": "ok", "message": f"Code reset for {name}"})


@app.route("/api/auth/admin/register_driver", methods=["POST"])
@admin_required
def api_auth_admin_register_driver():
    data = request.get_json(silent=True) or {}
    name = data.get("name", "").strip()
    if not name:
        return jsonify({"error": "missing driver name"}), 400
    return jsonify({"status": "ok", "name": name})


@app.route("/api/auth/admin/register_pm", methods=["POST"])
@pm_or_admin_required
def api_auth_admin_register_pm():
    data = request.get_json(silent=True) or {}
    email = data.get("email", "").strip()
    name = data.get("name", "").strip()
    password = data.get("password", "").strip()

    if not email or not name or not password:
        return jsonify({"error": "missing email, name, or password"}), 400

    try:
        from scheduling import create_pm_account
        pm = create_pm_account(email, name, password)
        return jsonify({"status": "ok", "pm": pm})
    except Exception as e:
        log.error(f"PM registration failed: {e}")
        return jsonify({"error": str(e)}), 400


### --- Scheduled Delivery endpoints --- ###

@app.route("/api/schedule/calendar/settings", methods=["GET"])
@pm_or_admin_required
def api_schedule_calendar_settings_get():
    try:
        settings = scheduling.get_calendar_settings()
        return jsonify({"settings": settings})
    except Exception as e:
        log.error(f"Calendar settings retrieval failed: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/schedule/calendar/settings", methods=["POST"])
@pm_or_admin_required
def api_schedule_calendar_settings_post():
    data = request.get_json(silent=True) or {}
    ics_url = data.get("ics_url", "").strip()

    try:
        scheduling.save_calendar_settings({"ics_url": ics_url})
        return jsonify({"status": "ok", "ics_url": ics_url})
    except Exception as e:
        log.error(f"Calendar settings save failed: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/schedule/calendar/upcoming")
@pm_or_admin_required
def api_schedule_calendar_upcoming():
    try:
        events = scheduling.upcoming_calendar_events()
        return jsonify({"events": events})
    except Exception as e:
        log.error(f"Upcoming events retrieval failed: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/schedule")
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

    required_fields = ["calendar_event_id", "job_number", "receiver_name", "receiver_email", "receiver_phone", "site_address", "assigned_driver", "pm_email"]
    missing = [f for f in required_fields if not data.get(f)]
    if missing:
        return jsonify({"error": f"missing fields: {', '.join(missing)}"}), 400

    try:
        delivery = scheduling.create_delivery(
            calendar_event_id=data["calendar_event_id"],
            job_number=data["job_number"],
            receiver_name=data["receiver_name"],
            receiver_email=data["receiver_email"],
            receiver_phone=data["receiver_phone"],
            site_address=data["site_address"],
            assigned_driver=data["assigned_driver"],
            pm_email=data["pm_email"],
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
    if not ticket_file:
        if request.form.get("generate_ticket") != "true":
            return jsonify({"error": "missing ticket file"}), 400

        line_items_raw = request.form.get("line_items")
        try:
            line_items = json.loads(line_items_raw) if line_items_raw else []
        except json.JSONDecodeError:
            return jsonify({"error": "line_items must be valid JSON"}), 400

        ticket_bytes = ticket_render.render_ticket(
            delivery,
            line_items=line_items,
        )
    else:
        ticket_bytes = ticket_file.read()

    record = scheduling.set_ticket(delivery_id, ticket_bytes)

    log.info(f"Ticket set for delivery {delivery_id}")
    return jsonify({"status": "ok", "delivery": record})


@app.route("/api/schedule/<delivery_id>/file/<n>")
@login_required
def api_schedule_file(delivery_id, n):
    delivery = scheduling.get_delivery(delivery_id)
    if not delivery:
        return jsonify({"error": f"no scheduled delivery found for id {delivery_id}"}), 404

    if n == "ticket":
        filepath = scheduling.ticket_file_path(delivery_id)
        if not os.path.exists(filepath):
            return jsonify({"error": "no ticket on file"}), 404
        return send_file(filepath, mimetype="image/jpeg", as_attachment=False)
    else:
        try:
            n_int = int(n)
        except ValueError:
            return jsonify({"error": "invalid file index"}), 400

        photo_filenames = delivery.get("photo_filenames") or []
        signature_filename = delivery.get("signature_filename")

        if n_int < len(photo_filenames):
            filepath = scheduling.delivery_file_path(delivery_id, photo_filenames[n_int])
        elif n_int == len(photo_filenames) and signature_filename:
            filepath = scheduling.delivery_file_path(delivery_id, signature_filename)
        else:
            return jsonify({"error": "file not found"}), 404

        if not os.path.exists(filepath):
            return jsonify({"error": "file not found"}), 404
        return send_file(filepath, mimetype="image/jpeg", as_attachment=False)


@app.route("/api/schedule/<delivery_id>/revise", methods=["POST"])
@pm_or_admin_required
def api_schedule_revise(delivery_id):
    delivery = scheduling.get_delivery(delivery_id)
    if not delivery:
        return jsonify({"error": f"no scheduled delivery found for id {delivery_id}"}), 404

    data = request.get_json(silent=True) or {}

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
    log.info(f"Delivery {delivery_id} revised: {updates}")
    return jsonify({"status": "ok", "delivery": record})


@app.route("/api/schedule/<delivery_id>/send_copy_to_pm", methods=["POST"])
@pm_or_admin_required
def api_schedule_send_copy_to_pm(delivery_id):
    delivery = scheduling.get_delivery(delivery_id)
    if not delivery:
        return jsonify({"error": f"no scheduled delivery found for id {delivery_id}"}), 404

    data = request.get_json(silent=True) or {}
    recipient_pm_email = data.get("pm_email")

    if not recipient_pm_email:
        return jsonify({"error": "missing pm_email"}), 400

    ticket_path = scheduling.ticket_file_path(delivery_id)
    if not os.path.exists(ticket_path):
        return jsonify({"error": "ticket not yet set"}), 400

    sent, err = emailer.send_flag_email(
        to_addr=recipient_pm_email,
        subject=f"[AES Logistics] Delivery ticket copy — Job #{delivery['job_number']}",
        body_text=f"Forwarding ticket for Job #{delivery['job_number']}.",
        attachment_paths=[ticket_path],
    )

    if not sent:
        log.error(f"Failed to send ticket copy to {recipient_pm_email}: {err}")
        return jsonify({"status": "error", "error": err}), 500

    log.info(f"Ticket for delivery {delivery_id} sent to {recipient_pm_email}")
    return jsonify({"status": "ok"})


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


@app.route("/api/schedule/driver/today")
@login_required
def api_schedule_driver_today():
    return jsonify({"deliveries": scheduling.deliveries_ready_for_driver()})


@app.route("/api/schedule/driver/mine")
@login_required
def api_schedule_driver_mine():
    driver_name = session.get("name")
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
    log.info(f"Delivery {delivery_id} started by driver {session.get('name')}. SMS sent: {sms_sent}. ETA: {eta}")

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
            photo_buffers=photo_buffers
        )
        
        log.info(f"AES upload result for delivery {delivery_id}: {len(aes_result['uploaded'])} files processed")
        
    except Exception as e:
        log.error(f"Error uploading to AES: {str(e)}")
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
    return jsonify({"status": "ok", "delivery": record})


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

    dest_dir = os.path.join(CFG["incoming_slip_subfolder"], f"Job_{job_number}")
    final_path = unique_destination(dest_dir, f"packing_slip_{slip_id}")
    os.makedirs(os.path.dirname(final_path), exist_ok=True)
    shutil.move(slip_path, final_path)

    record = inventory.log_packing_slip(job_number, po_number, slip_id)
    log.info(f"Packing slip {slip_id} filed for Job #{job_number}")

    return jsonify({"status": "ok", "entry": record})


@app.route("/api/incoming/flag", methods=["POST"])
@login_required
def api_incoming_flag():
    data = request.get_json(silent=True) or {}
    slip_id = data.get("slip_id", "").strip()
    reason = data.get("reason", "no job number").strip()

    if not slip_id:
        return jsonify({"error": "missing slip_id"}), 400

    slip_path = os.path.join(CFG["incoming_staging_dir"], slip_id)
    if not os.path.exists(slip_path):
        return jsonify({"error": "slip not found"}), 404

    flagged_dir = os.path.join(CFG["dest_dir"], CFG.get("flagged_slips_folder", "flagged_packing_slips"))
    final_path = unique_destination(flagged_dir, slip_id)
    os.makedirs(os.path.dirname(final_path), exist_ok=True)
    shutil.move(slip_path, final_path)

    sent, err = emailer.send_flag_email(
        to_addr=CFG.get("flag_alert_email_to", "PMteam@aes-energy.com"),
        subject="[AES Logistics] Flagged packing slip — could not read job number",
        body_text=f"A packing slip could not be processed. Reason: {reason}.",
        attachment_paths=[final_path] if os.path.exists(final_path) else [],
    )

    log.info(f"Packing slip {slip_id} flagged and emailed to PM team. Email sent: {sent}")
    return jsonify({"status": "ok", "email_sent": sent, "email_error": err})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
