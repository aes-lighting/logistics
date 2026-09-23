# ── server/server_config.json · reference/normalized copy ──
# Live OCR regexes + folder layout. Named groups are REQUIRED by extract_*().
{
  "job_number_pattern": "job\\s*#?\\s*:?\\s*(?P<job>\\d{3,8})",
  "po_number_pattern": "p\\.?\\s*o\\.?\\s*#?\\s*:?\\s*(?P<po>[A-Za-z0-9\\-]{3,20})",

  "incoming_dir": "./incoming",
  "dest_dir": "./organized",
  "review_folder": "needs_review_no_job_number",
  "incomplete_flag_filename": "INCOMPLETE_missing_pallet_photo.txt",

  "incoming_staging_dir": "./incoming/_staging",
  "incoming_slip_subfolder": "Incoming_Packing_Slips",
  "flagged_slips_folder": "flagged_packing_slips",

  "flag_alert_email_to": "PMteam@aes-energy.com",
  "warehouse_alert_email": "Warehouse@aes-energy.com"
}
# Notes: patterns are placeholders — tune against real slips/tickets together
# with any code that consumes them. Production should use absolute data roots.