"""
scheduling.py

Scheduled Delivery flow: a PM sees upcoming calendar events (from a
read-only ICS feed), sets one up as a delivery (job number, receiver
name/email), uploads the delivery ticket, and the driver app then shows that
ticket for check-off + photos + signature on delivery day. Once complete,
the signed result is emailed to the PM and the receiver automatically.

This is separate from the ad-hoc "New Delivery" flow — that one still
exists for deliveries that were never scheduled in advance.

Storage: a JSON file (schedule_store.json) next to this module. Ticket
uploads and signed outputs live under <BASE_DIR>/schedule_files/<delivery_id>/.
"""

import json
import logging
import os
import uuid
from datetime import datetime, timedelta

import requests
from icalendar import Calendar

log = logging.getLogger("aes_logistics.scheduling")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STORE_PATH = os.path.join(BASE_DIR, "schedule_store.json")
FILES_DIR = os.path.join(BASE_DIR, "schedule_files")

os.makedirs(FILES_DIR, exist_ok=True)


def _load_store():
    if not os.path.isfile(STORE_PATH):
        return {"deliveries": {}, "settings": {"ics_url": None}}
    with open(STORE_PATH, "r") as f:
        return json.load(f)


def _save_store(store):
    with open(STORE_PATH, "w") as f:
        json.dump(store, f, indent=2)


# ---------- Settings (the ICS feed URL) ----------

def set_ics_url(url):
    store = _load_store()
    store["settings"]["ics_url"] = url
    _save_store(store)


def get_ics_url():
    return _load_store()["settings"].get("ics_url")


# ---------- Calendar sync (read-only) ----------

def fetch_upcoming_events(days_ahead=14):
    """
    Fetches and parses the configured ICS feed. Returns a list of
    { uid, title, start_iso } for events in [now, now + days_ahead], sorted
    by start time. Returns [] with a logged warning if no feed is configured
    or the fetch/parse fails — this must never crash the caller.
    """
    url = get_ics_url()
    if not url:
        return []

    try:
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
        cal = Calendar.from_ical(resp.content)
    except Exception as e:
        log.error(f"Failed to fetch/parse ICS feed: {e}")
        return []

    now = datetime.now()
    cutoff = now + timedelta(days=days_ahead)
    events = []

    for component in cal.walk():
        if component.name != "VEVENT":
            continue
        try:
            dtstart = component.get("dtstart").dt
            # dtstart can be a date or datetime depending on the event
            if hasattr(dtstart, "hour"):
                start = dtstart.replace(tzinfo=None)
            else:
                start = datetime(dtstart.year, dtstart.month, dtstart.day)
        except Exception:
            continue

        if now.date() <= start.date() <= cutoff.date():
            events.append({
                "uid": str(component.get("uid", "")),
                "title": str(component.get("summary", "(no title)")),
                "start_iso": start.isoformat(),
            })

    events.sort(key=lambda e: e["start_iso"])
    return events


def linked_event_uids():
    store = _load_store()
    return {d.get("calendar_event_uid") for d in store["deliveries"].values() if d.get("calendar_event_uid")}


# ---------- Scheduled deliveries CRUD ----------

def create_delivery(job_number, delivery_date, receiver_name, receiver_email, pm_email, site_address="", calendar_event_uid=None, assigned_driver=None, receiver_phone=None,
                     customer_name="", customer_po="", job_name="", delivery_method=""):
    delivery_id = str(uuid.uuid4())
    store = _load_store()
    store["deliveries"][delivery_id] = {
        "id": delivery_id,
        "job_number": job_number,
        "delivery_date": delivery_date,  # "YYYY-MM-DD"
        "receiver_name": receiver_name,
        "receiver_email": receiver_email,
        "receiver_phone": receiver_phone,
        "pm_email": pm_email,
        "site_address": site_address,
        "customer_name": customer_name,
        "customer_po": customer_po,
        "job_name": job_name,
        "delivery_method": delivery_method,
        "calendar_event_uid": calendar_event_uid,
        "assigned_driver": assigned_driver,
        "status": "scheduled",  # scheduled -> ticket_uploaded -> packed -> en_route -> completed
        "ticket_filename": None,
        "ticket_source": None,  # "uploaded" or "generated"
        "line_items": [],  # [{"description", "quantity", "type", "model_number", "mfg", "boxes"}] — only set if generated w/ items
        "reminder_sent": False,
        "created_at": datetime.now().isoformat(),
        "packed_confirmed": False,
        "packed_by": None,
        "packed_signature_filename": None,
        "packed_at": None,
        "line_item_checks": [],  # warehouse "LOADED" checkoff, one bool per line item
        "started_at": None,
        "eta": None,
        "completed_at": None,
        "checkoff_confirmed": False,
        "unload_item_checks": [],  # driver "DELIVERED" checkoff, one bool per line item
        "signature_filename": None,
        "signed_by": None,
        "photo_filenames": [],
        "geotag": None,
    }
    _save_store(store)
    return store["deliveries"][delivery_id]


def list_deliveries():
    store = _load_store()
    return sorted(store["deliveries"].values(), key=lambda d: d["delivery_date"])


def get_delivery(delivery_id):
    store = _load_store()
    return store["deliveries"].get(delivery_id)


def deliveries_needing_reminder():
    """Deliveries scheduled for tomorrow that don't have a ticket yet and haven't been reminded."""
    tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
    store = _load_store()
    return [
        d for d in store["deliveries"].values()
        if d["delivery_date"] == tomorrow and not d["ticket_filename"] and not d["reminder_sent"]
    ]


def mark_reminder_sent(delivery_id):
    store = _load_store()
    if delivery_id in store["deliveries"]:
        store["deliveries"][delivery_id]["reminder_sent"] = True
        _save_store(store)


def deliveries_ready_for_driver(date_str=None):
    """Deliveries that are packed (warehouse checked off + signed), for a
    given date (default today), not yet completed. Not visible to a driver
    before packing happens."""
    date_str = date_str or datetime.now().strftime("%Y-%m-%d")
    store = _load_store()
    return [
        d for d in store["deliveries"].values()
        if d["delivery_date"] == date_str and d["status"] in ("packed", "en_route")
    ]


def deliveries_assigned_to(driver_name):
    """
    A driver's full list of deliveries: anything assigned to them that has
    been packed (or is already en route), not yet completed, regardless of
    date. A ticket that's only uploaded/generated but not yet packed by
    warehouse does NOT show here — packing has to happen first.
    """
    if not driver_name:
        return []
    name_key = driver_name.strip().lower()
    store = _load_store()
    return sorted(
        [
            d for d in store["deliveries"].values()
            if d["status"] in ("packed", "en_route")
            and (d.get("assigned_driver") or "").strip().lower() == name_key
        ],
        key=lambda d: d["delivery_date"],
    )


def deliveries_ready_to_pack():
    """Deliveries with a ticket (uploaded or generated) that warehouse hasn't packed/signed yet."""
    store = _load_store()
    return sorted(
        [d for d in store["deliveries"].values() if d["status"] == "ticket_uploaded"],
        key=lambda d: d["delivery_date"],
    )


def pack_delivery(delivery_id, line_item_checks, packed_by, signature_file_storage):
    """
    Warehouse's outgoing-inventory step: confirms items were checked off
    while packing, records who packed it, and captures their signature.
    Returns the updated record, or None if delivery_id is invalid.
    """
    store = _load_store()
    if delivery_id not in store["deliveries"]:
        return None

    delivery_dir = os.path.join(FILES_DIR, delivery_id)
    os.makedirs(delivery_dir, exist_ok=True)

    sig_filename = "packed_signature.png"
    signature_file_storage.save(os.path.join(delivery_dir, sig_filename))

    record = store["deliveries"][delivery_id]
    record["line_item_checks"] = line_item_checks
    record["packed_by"] = packed_by
    record["packed_signature_filename"] = sig_filename
    record["packed_confirmed"] = True
    record["status"] = "packed"
    record["packed_at"] = datetime.now().isoformat()
    _save_store(store)
    return record


def start_delivery(delivery_id, eta_info):
    """
    Marks a delivery as en route. eta_info is whatever maps.get_eta()
    returned (or None if unavailable) — stored as-is for the PM portal to
    display later.
    """
    store = _load_store()
    if delivery_id not in store["deliveries"]:
        return None
    record = store["deliveries"][delivery_id]
    record["status"] = "en_route"
    record["started_at"] = datetime.now().isoformat()
    record["eta"] = eta_info
    _save_store(store)
    return record


def save_ticket_file(delivery_id, file_storage):
    store = _load_store()
    if delivery_id not in store["deliveries"]:
        return None
    delivery_dir = os.path.join(FILES_DIR, delivery_id)
    os.makedirs(delivery_dir, exist_ok=True)

    ext = os.path.splitext(file_storage.filename or "ticket.jpg")[1] or ".jpg"
    filename = f"ticket{ext}"
    path = os.path.join(delivery_dir, filename)
    file_storage.save(path)

    store["deliveries"][delivery_id]["ticket_filename"] = filename
    store["deliveries"][delivery_id]["ticket_source"] = "uploaded"
    store["deliveries"][delivery_id]["status"] = "ticket_uploaded"
    _save_store(store)
    return path


def save_generated_ticket(delivery_id, image_bytes, line_items, pm_name=""):
    """Saves a PM-generated ticket image (rendered server-side) and stores the line items."""
    store = _load_store()
    if delivery_id not in store["deliveries"]:
        return None
    delivery_dir = os.path.join(FILES_DIR, delivery_id)
    os.makedirs(delivery_dir, exist_ok=True)

    filename = "ticket_generated.png"
    with open(os.path.join(delivery_dir, filename), "wb") as f:
        f.write(image_bytes)

    store["deliveries"][delivery_id]["ticket_filename"] = filename
    store["deliveries"][delivery_id]["ticket_source"] = "generated"
    store["deliveries"][delivery_id]["line_items"] = line_items
    store["deliveries"][delivery_id]["pm_name"] = pm_name
    store["deliveries"][delivery_id]["status"] = "ticket_uploaded"
    _save_store(store)
    return store["deliveries"][delivery_id]


def ticket_file_path(delivery_id):
    d = get_delivery(delivery_id)
    if not d or not d.get("ticket_filename"):
        return None
    return os.path.join(FILES_DIR, delivery_id, d["ticket_filename"])


def complete_delivery(delivery_id, checkoff_confirmed, signed_by, signature_file_storage, photo_file_storages, geotag, unload_item_checks=None):
    """
    Finalizes a scheduled delivery: saves the signature + photos, marks
    complete. unload_item_checks is the driver's per-line-item "DELIVERED"
    checkoff (one bool per line item) — empty/None when the ticket has no
    structured line items, in which case checkoff_confirmed (a single
    overall box) is used instead. Returns the updated record, or None if
    delivery_id is invalid. Caller (app.py) is responsible for emailing
    PM + receiver afterward.
    """
    store = _load_store()
    if delivery_id not in store["deliveries"]:
        return None

    delivery_dir = os.path.join(FILES_DIR, delivery_id)
    os.makedirs(delivery_dir, exist_ok=True)

    sig_filename = "signature.png"
    signature_file_storage.save(os.path.join(delivery_dir, sig_filename))

    photo_filenames = []
    for i, photo in enumerate(photo_file_storages, start=1):
        ext = os.path.splitext(photo.filename or f"photo{i}.jpg")[1] or ".jpg"
        pname = f"photo_{i}{ext}"
        photo.save(os.path.join(delivery_dir, pname))
        photo_filenames.append(pname)

    record = store["deliveries"][delivery_id]
    record["checkoff_confirmed"] = bool(checkoff_confirmed)
    record["unload_item_checks"] = unload_item_checks or []
    record["signed_by"] = signed_by
    record["signature_filename"] = sig_filename
    record["photo_filenames"] = photo_filenames
    record["geotag"] = geotag
    record["status"] = "completed"
    record["completed_at"] = datetime.now().isoformat()
    _save_store(store)
    return record


def delivery_file_path(delivery_id, filename):
    return os.path.join(FILES_DIR, delivery_id, filename)
