# Spec 001 — Server API: Data Model

Persistence is JSON-on-disk. Two mutable stores + filesystem dirs + legacy inert file.

## `server/schedule_store.json`
```
{
  "deliveries": {
    "<uuid>": {
      id, job_number, delivery_date ("YYYY-MM-DD"),
      receiver_name, receiver_email, receiver_phone, pm_email, site_address,
      customer_name, customer_po, job_name, delivery_method, calendar_event_uid,
      assigned_driver,
      status: "scheduled"|"ticket_uploaded"|"packed"|"en_route"|"completed",
      ticket_filename, ticket_source: "uploaded"|"generated",
      line_items: [{description, quantity, type, boxes, model_number, mfg}],
      reminder_sent, created_at,
      packed_confirmed, packed_by, packed_signature_filename, packed_at,
      line_item_checks: [bool...],            # warehouse LOADED
      revision_count, last_revised_at,
      started_at, eta,                        # eta = maps.get_eta() dict or None
      completed_at, checkoff_confirmed,
      unload_item_checks: [bool...],          # driver DELIVERED
      signature_filename, signed_by, photo_filenames: [..], geotag: {lat,lng}|None,
      pm_name
    }
  },
  "settings": { "ics_url": "<read-only ICS feed>" }
}
```

## `server/inventory_store.json`
```
{
  "entries": {
    "<uuid>": {
      id, job_number, po_number, pm_email, confirmed_by, confirmed_at,
      slip_photo_filenames: [], pallet_count, pallet_photo_filenames: [],
      locations: [{"location": str, "count": int}],  # split allowed; sums = pallet_count
      comment, qr_pdf_filename,
      removed: bool, removed_at, removed_reason     # "packed_for_outgoing_delivery" | manual
    }
  },
  "job_pm_directory": { "<job_number>": "<pm_email>" }   # memo: first-seen PM per job
}
```

## Filesystem
- `server/schedule_files/<delivery_id>/` — `ticket.jpg|.png`, `packed_signature.png`,
  `signature.png`, `photo_<i>.jpg|.png`.
- `incoming/` (root default) — `organized/Job_<n>/`, `needs_review_no_job_number/<id>/`,
  `Incoming_Packing_Slips/Job_<n>/`, `flagged_packing_slips/`, `_staging/` (slip scans),
  `INCOMPLETE_missing_pallet_photo.txt` flag.
- 13 fixed `LOCATIONS` in `inventory.py` (Warehouse, Back Tent, Front Tent,
  Trailer 6, Trailer 4, Redbox, Front Red, CS 1036, CS 1071, CS 1058, CS 1015,
  Office, Truck).

## Invariants
- Locations per entry may split; total counts must equal `pallet_count`.
  Enforced **server-side** in `POST /api/incoming/finalize` (and client-side in
  the wizard); each location must be one of the 13 `LOCATIONS`.
- A delivery is driver-visible only when `status in {packed, en_route}` and it
  matches the driver's name (case-insensitive) — enforced in `deliveries_assigned_to`.
- Packing a delivery auto-marks matching job-number inventory entries removed
  (`mark_removed_by_job`). Manual Mark Shipped covers partials.
- No locking/transactions: last-writer-whole-file. Suitable for single-instance
  small fleet; not safe for clustered deploy.