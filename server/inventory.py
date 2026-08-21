"""
inventory.py

Tracks where incoming items physically end up once checked in — a running
record of "what's here and where," not just a folder of filed photos. Each
time a warehouse worker confirms an Incoming Inventory scan, one entry is
added here with the location they tagged it with.

This is intentionally separate from the scheduling.py delivery lifecycle —
it's a location ledger, not a delivery record. An item can be logged in here
long before (or without ever being part of) a scheduled outgoing delivery.
"""

import json
import os
import uuid
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STORE_PATH = os.path.join(BASE_DIR, "inventory_store.json")

LOCATIONS = ["Warehouse", "Tent 1", "Tent 2", "Econoboxes"]


def _load_store():
    if not os.path.isfile(STORE_PATH):
        return {"entries": {}}
    with open(STORE_PATH, "r") as f:
        return json.load(f)


def _save_store(store):
    with open(STORE_PATH, "w") as f:
        json.dump(store, f, indent=2)


def add_entry(job_number, location, confirmed_by, photo_filename=None, note=""):
    """Records one incoming item as checked in at a given location."""
    entry_id = str(uuid.uuid4())
    store = _load_store()
    store["entries"][entry_id] = {
        "id": entry_id,
        "job_number": job_number,
        "location": location,
        "confirmed_by": confirmed_by,
        "confirmed_at": datetime.now().isoformat(),
        "photo_filename": photo_filename,
        "note": note,
        "removed": False,
        "removed_at": None,
    }
    _save_store(store)
    return store["entries"][entry_id]


def list_entries(include_removed=False):
    store = _load_store()
    entries = list(store["entries"].values())
    if not include_removed:
        entries = [e for e in entries if not e.get("removed")]
    return sorted(entries, key=lambda e: e["confirmed_at"], reverse=True)


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
