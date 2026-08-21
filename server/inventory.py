"""
inventory.py

Tracks incoming shipments checked in via Incoming Inventory: the packing
slip (possibly multiple pages), the PO number and job number, pallet count
and a photo of each pallet, which location(s) it was put in (can be split
across several), a comment, and who confirmed it. Also maintains a simple
job-number -> PM-email directory so the right project manager gets emailed
automatically without having to be picked every single time.

This is intentionally separate from the scheduling.py delivery lifecycle —
it's a receiving/location ledger, not a delivery record.
"""

import json
import os
import uuid
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STORE_PATH = os.path.join(BASE_DIR, "inventory_store.json")

LOCATIONS = [
    "Warehouse", "Back Tent", "Front Tent", "Trailer 6", "Trailer 4",
    "Redbox", "Front Red", "CS 1036", "CS 1071", "CS 1058", "CS 1015",
    "Office", "Truck",
]


def _load_store():
    if not os.path.isfile(STORE_PATH):
        return {"entries": {}, "job_pm_directory": {}}
    with open(STORE_PATH, "r") as f:
        store = json.load(f)
    store.setdefault("entries", {})
    store.setdefault("job_pm_directory", {})
    return store


def _save_store(store):
    with open(STORE_PATH, "w") as f:
        json.dump(store, f, indent=2)


# ---------- Job -> PM directory ----------

def get_pm_for_job(job_number):
    """Returns the pm_email already on file for this job, or None if it's never been set."""
    store = _load_store()
    return store["job_pm_directory"].get((job_number or "").strip())


def set_pm_for_job(job_number, pm_email):
    store = _load_store()
    store["job_pm_directory"][(job_number or "").strip()] = pm_email
    _save_store(store)


# ---------- Entries ----------

def add_entry(job_number, po_number, confirmed_by, slip_photo_filenames,
              pm_email, pallet_count=1, pallet_photo_filenames=None,
              locations=None, comment="", qr_pdf_filename=None):
    """
    locations: list of {"location": str, "count": int} — supports splitting
    a shipment's pallets across multiple storage locations. If only one
    location was used, this is just a single-item list.
    """
    entry_id = str(uuid.uuid4())
    store = _load_store()
    store["entries"][entry_id] = {
        "id": entry_id,
        "job_number": job_number,
        "po_number": po_number,
        "pm_email": pm_email,
        "confirmed_by": confirmed_by,
        "confirmed_at": datetime.now().isoformat(),
        "slip_photo_filenames": slip_photo_filenames or [],
        "pallet_count": pallet_count,
        "pallet_photo_filenames": pallet_photo_filenames or [],
        "locations": locations or [],
        "comment": comment,
        "qr_pdf_filename": qr_pdf_filename,
        "removed": False,
        "removed_at": None,
        "removed_reason": None,
    }
    _save_store(store)
    return store["entries"][entry_id]


def get_entry(entry_id):
    store = _load_store()
    return store["entries"].get(entry_id)


def set_qr_pdf_filename(entry_id, filename):
    store = _load_store()
    if entry_id not in store["entries"]:
        return None
    store["entries"][entry_id]["qr_pdf_filename"] = filename
    _save_store(store)
    return store["entries"][entry_id]


def list_entries(include_removed=False):
    store = _load_store()
    entries = list(store["entries"].values())
    if not include_removed:
        entries = [e for e in entries if not e.get("removed")]
    return sorted(entries, key=lambda e: e["confirmed_at"], reverse=True)


def list_entries_for_date(date_str):
    """date_str: 'YYYY-MM-DD'. Used by the end-of-day report."""
    store = _load_store()
    return sorted(
        [e for e in store["entries"].values() if e["confirmed_at"][:10] == date_str],
        key=lambda e: e["confirmed_at"],
    )


def mark_removed(entry_id):
    """Manually mark one entry as no longer at that location (e.g. a correction, or a partial shipment)."""
    store = _load_store()
    if entry_id not in store["entries"]:
        return None
    store["entries"][entry_id]["removed"] = True
    store["entries"][entry_id]["removed_at"] = datetime.now().isoformat()
    _save_store(store)
    return store["entries"][entry_id]


def mark_removed_by_job(job_number):
    """
    Called when an outgoing delivery for this job is packed — marks every
    still-active inventory entry under that job number as shipped out.

    This is a job-number-level link, not item-level: there's no shared SKU
    system between what arrived (Incoming Inventory) and what's on an
    outgoing ticket's line items, so packing a delivery for Job #X clears
    all of Job #X's currently-logged locations, on the assumption that
    what's shipping is what was received for that job. If a job's material
    arrives and ships in partial batches, use the manual "Mark Shipped"
    action in the PM portal instead for finer control.

    Returns the number of entries marked removed.
    """
    store = _load_store()
    job_key = (job_number or "").strip()
    count = 0
    for entry in store["entries"].values():
        if entry["job_number"] == job_key and not entry.get("removed"):
            entry["removed"] = True
            entry["removed_at"] = datetime.now().isoformat()
            entry["removed_reason"] = "packed_for_outgoing_delivery"
            count += 1
    if count:
        _save_store(store)
    return count
