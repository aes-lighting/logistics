"""
maps.py

Computes a driving ETA from the driver's current GPS coordinates to the
delivery's site address, using Google's Distance Matrix API. Like sms.py
and emailer.py, this degrades gracefully — if it isn't configured or the
API call fails for any reason, it returns None instead of raising, so a
delivery can still start (and the "on the way" text still sends) without an
ETA rather than blocking on it.

Required environment variable (see .env.example):
    GOOGLE_MAPS_API_KEY

Getting one: Google Cloud Console -> APIs & Services -> enable "Distance
Matrix API" -> Credentials -> create an API key. Billing must be enabled on
the project (Google requires a card on file even though there's a free
monthly quota that covers light use).
"""

import logging
import os
from datetime import datetime, timedelta

import requests

log = logging.getLogger("aes_logistics.maps")

DISTANCE_MATRIX_URL = "https://maps.googleapis.com/maps/api/distancematrix/json"


def get_eta(origin_lat, origin_lng, destination_address):
    """
    Returns { "duration_minutes": int, "duration_text": str, "distance_text": str,
              "arrival_time_iso": str } or None if unavailable for any reason.
    """
    api_key = os.environ.get("GOOGLE_MAPS_API_KEY")
    if not api_key:
        log.warning("ETA not calculated — GOOGLE_MAPS_API_KEY not configured.")
        return None
    if not destination_address:
        log.warning("ETA not calculated — no site address on file for this delivery.")
        return None

    try:
        resp = requests.get(
            DISTANCE_MATRIX_URL,
            params={
                "origins": f"{origin_lat},{origin_lng}",
                "destinations": destination_address,
                "mode": "driving",
                "key": api_key,
            },
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()

        if data.get("status") != "OK":
            log.error(f"Distance Matrix API returned status: {data.get('status')}")
            return None

        element = data["rows"][0]["elements"][0]
        if element.get("status") != "OK":
            log.error(f"Distance Matrix element status: {element.get('status')} (destination may not be a valid address)")
            return None

        duration_seconds = element["duration"]["value"]
        duration_minutes = round(duration_seconds / 60)
        arrival_time = datetime.now() + timedelta(seconds=duration_seconds)

        return {
            "duration_minutes": duration_minutes,
            "duration_text": element["duration"]["text"],
            "distance_text": element["distance"]["text"],
            "arrival_time_iso": arrival_time.isoformat(),
        }
    except Exception as e:
        log.error(f"Failed to fetch ETA: {e}")
        return None
