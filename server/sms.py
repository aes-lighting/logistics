"""
sms.py

Sends "driver is on the way" texts via Twilio. Like emailer.py, this never
crashes the caller if it isn't configured yet — it returns (False, reason)
instead, so a missing Twilio setup never blocks a delivery from starting.

Required environment variables (see .env.example):
    TWILIO_ACCOUNT_SID
    TWILIO_AUTH_TOKEN
    TWILIO_FROM_NUMBER   (a Twilio phone number in E.164 format, e.g. +15551234567)

Getting these: sign up at twilio.com, buy/verify a phone number capable of
SMS, and copy the Account SID + Auth Token from the console dashboard. A
trial account works for testing but can only text verified numbers until
upgraded to a paid account.
"""

import logging
import os

log = logging.getLogger("aes_logistics.sms")


def _twilio_settings():
    sid = os.environ.get("TWILIO_ACCOUNT_SID")
    token = os.environ.get("TWILIO_AUTH_TOKEN")
    from_number = os.environ.get("TWILIO_FROM_NUMBER")
    if not all([sid, token, from_number]):
        return None
    return {"sid": sid, "token": token, "from_number": from_number}


def send_sms(to_number, body):
    """
    Returns (success: bool, error_message_or_None)
    """
    settings = _twilio_settings()
    if not settings:
        log.warning("SMS not sent — TWILIO_ACCOUNT_SID/TWILIO_AUTH_TOKEN/TWILIO_FROM_NUMBER not configured.")
        return False, "SMS not configured (see .env.example)"

    if not to_number:
        return False, "No receiver phone number on file for this delivery."

    try:
        from twilio.rest import Client

        client = Client(settings["sid"], settings["token"])
        client.messages.create(body=body, from_=settings["from_number"], to=to_number)
        log.info(f"SMS sent to {to_number}")
        return True, None
    except Exception as e:
        log.error(f"Failed to send SMS to {to_number}: {e}")
        return False, str(e)
