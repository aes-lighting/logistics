"""
emailer.py

Sends flagged-packing-slip alert emails. Credentials come from environment
variables (or a .env file) — never from server_config.json — so they don't
end up committed to version control or handed around in a JSON file.

Required environment variables (see .env.example):
    SMTP_HOST
    SMTP_PORT
    SMTP_USERNAME
    SMTP_PASSWORD
    SMTP_FROM
    SMTP_USE_TLS      ("true"/"false", default "true")

If these aren't set, send_flag_email() returns (False, "not configured")
instead of raising, so a missing email setup never crashes the upload flow.
"""

import logging
import os
import smtplib
from email.message import EmailMessage

log = logging.getLogger("aes_logistics.emailer")


def _smtp_settings():
    host = os.environ.get("SMTP_HOST")
    port = os.environ.get("SMTP_PORT")
    username = os.environ.get("SMTP_USERNAME")
    password = os.environ.get("SMTP_PASSWORD")
    sender = os.environ.get("SMTP_FROM")
    use_tls = os.environ.get("SMTP_USE_TLS", "true").lower() != "false"

    if not all([host, port, sender]):
        return None

    return {
        "host": host,
        "port": int(port),
        "username": username,
        "password": password,
        "sender": sender,
        "use_tls": use_tls,
    }


def send_flag_email(to_addr, subject, body_text, attachment_path=None, attachment_paths=None):
    """
    Returns (success: bool, error_message_or_None)
    attachment_path: single file (kept for backward compatibility)
    attachment_paths: list of files — use this for multiple attachments
    """
    settings = _smtp_settings()
    if not settings:
        log.warning("Email not sent — SMTP_HOST/SMTP_PORT/SMTP_FROM not configured in environment.")
        return False, "SMTP not configured (see .env.example)"

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = settings["sender"]
    msg["To"] = to_addr
    msg.set_content(body_text)

    all_paths = list(attachment_paths or [])
    if attachment_path:
        all_paths.append(attachment_path)

    for path in all_paths:
        if not path or not os.path.isfile(path):
            continue
        with open(path, "rb") as f:
            data = f.read()
        filename = os.path.basename(path)
        maintype = "image"
        subtype = os.path.splitext(filename)[1].lstrip(".").lower() or "jpeg"
        if subtype == "pdf":
            maintype, subtype = "application", "pdf"
        msg.add_attachment(data, maintype=maintype, subtype=subtype, filename=filename)

    try:
        with smtplib.SMTP(settings["host"], settings["port"], timeout=15) as server:
            if settings["use_tls"]:
                server.starttls()
            if settings["username"] and settings["password"]:
                server.login(settings["username"], settings["password"])
            server.send_message(msg)
        log.info(f"Flag email sent to {to_addr}")
        return True, None
    except Exception as e:
        log.error(f"Failed to send flag email: {e}")
        return False, str(e)
