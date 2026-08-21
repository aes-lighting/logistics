#!/usr/bin/env python3
"""
send_daily_inventory_report.py

Run once at the end of the day (via cron) to email a summary of everything
checked in via Incoming Inventory that day — job/PO numbers, pallet counts,
locations, comments, and clickable links to view each entry's photos.

Recipients: every registered PM and Admin account. If "everyone" should mean
something broader (e.g. drivers too), that's a one-line change below.

Suggested cron entry (once daily, e.g. 6pm):
    0 18 * * * cd /path/to/aes_logistics/server && /path/to/venv/bin/python3 send_daily_inventory_report.py >> /var/log/aes_logistics/daily_report.log 2>&1

The clickable links point at the app itself and require being logged in —
that's expected for an internal tool; clicking one while already logged in
elsewhere in the browser goes straight through.
"""

import logging
import os
import sys
from datetime import datetime

from dotenv import load_dotenv

import auth
import emailer
import inventory

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("aes_logistics.daily_report")


def build_report_body(entries, base_url):
    if not entries:
        return "No packing slips were checked in today."

    lines = [f"{len(entries)} packing slip(s) checked in today:\n"]
    for e in entries:
        locations_str = ", ".join(f"{loc['location']} ({loc['count']})" for loc in e.get("locations", []))
        detail_url = f"{base_url.rstrip('/')}/inventory/{e['id']}"
        lines.append(
            f"- Job #{e['job_number']}"
            + (f" / PO {e['po_number']}" if e.get("po_number") else "")
            + f"\n  Pallets: {e.get('pallet_count', '?')}  |  Location(s): {locations_str or '(none)'}"
            + f"\n  Checked in by: {e.get('confirmed_by') or '(unknown)'} at {e['confirmed_at'][11:19]}"
            + (f"\n  Comment: {e['comment']}" if e.get("comment") else "")
            + f"\n  View photos/slip: {detail_url}"
            + "\n"
        )
    return "\n".join(lines)


def main():
    base_url = os.environ.get("PUBLIC_BASE_URL")
    if not base_url:
        log.warning(
            "PUBLIC_BASE_URL not set in .env — links in the report will be relative and may not open correctly. "
            "Add PUBLIC_BASE_URL=https://your-domain-or-tunnel-url to .env."
        )
        base_url = ""

    today = datetime.now().strftime("%Y-%m-%d")
    entries = inventory.list_entries_for_date(today)
    log.info(f"{len(entries)} entr(ies) checked in today ({today}).")

    body = build_report_body(entries, base_url)
    subject = f"[AES Logistics] Daily Incoming Inventory Report — {today} ({len(entries)} item(s))"

    recipients = [u["email"] for u in auth.list_users() if u["role"] in ("pm", "admin")]
    if not recipients:
        log.warning("No PM/admin accounts registered — nothing to send the report to.")
        return

    for to_addr in recipients:
        sent, err = emailer.send_flag_email(to_addr=to_addr, subject=subject, body_text=body)
        if sent:
            log.info(f"Daily report sent to {to_addr}")
        else:
            log.error(f"Failed to send daily report to {to_addr}: {err}")


if __name__ == "__main__":
    main()
