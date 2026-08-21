#!/usr/bin/env python3
"""
send_reminders.py

Run once a day (via cron) to email PMs reminding them to upload the delivery
ticket for anything scheduled tomorrow that doesn't have one yet.

Suggested cron entry (once daily, e.g. 8am):
    0 8 * * * cd /path/to/aes_logistics/server && /path/to/venv/bin/python3 send_reminders.py >> /var/log/aes_logistics/reminders.log 2>&1

This is intentionally a separate script from app.py (not an HTTP endpoint)
so it only does one job and is easy to schedule independently.
"""

import logging
import sys

from dotenv import load_dotenv

import emailer
import scheduling

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("aes_logistics.reminders")


def main():
    due = scheduling.deliveries_needing_reminder()
    log.info(f"{len(due)} delivery(ies) need a reminder sent.")

    for delivery in due:
        subject = f"[AES Logistics] Delivery ticket needed for tomorrow — Job #{delivery['job_number']}"
        body = (
            f"A delivery is scheduled for tomorrow ({delivery['delivery_date']}) and doesn't have a "
            f"delivery ticket uploaded yet.\n\n"
            f"Job number: {delivery['job_number']}\n"
            f"Receiver: {delivery['receiver_name']} <{delivery['receiver_email']}>\n"
            f"Site: {delivery.get('site_address') or '(not provided)'}\n\n"
            f"Please log into the PM portal and upload the ticket so it's ready for the driver:\n"
            f"  (your server URL)/pm\n"
        )
        sent, err = emailer.send_flag_email(
            to_addr=delivery["pm_email"],
            subject=subject,
            body_text=body,
        )
        if sent:
            scheduling.mark_reminder_sent(delivery["id"])
            log.info(f"Reminder sent to {delivery['pm_email']} for Job #{delivery['job_number']}")
        else:
            log.error(f"Failed to send reminder for Job #{delivery['job_number']}: {err}")


if __name__ == "__main__":
    main()
