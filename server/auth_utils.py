"""
Authentication utilities for AES Logistics API.
Handles auth-service integration and header extraction.
"""
import os
import requests
from flask import request
import logging

log = logging.getLogger(__name__)

# Auth-service configuration
AUTH_SERVICE_URL = os.getenv(
    "AUTH_SERVICE_URL",
    "https://auth-service-production-bb0d.up.railway.app"
)


def get_auth_header():
    """
    Extract user email from Authorization header.

    Returns:
        str: User email if found, None otherwise

    Examples:
        Authorization: Bearer user@example.com
        → returns "user@example.com"
    """
    auth_header = request.headers.get("Authorization", "")

    # Extract email from "Bearer <email>" format
    if auth_header.startswith("Bearer "):
        return auth_header[7:].strip()

    # Fallback: check JSON body for "email" field (for POST requests)
    try:
        data = request.get_json(silent=True) or {}
        if "email" in data:
            return data["email"].strip().lower()
    except Exception:
        pass

    # Fallback: check form data "metadata" field containing driver name
    try:
        metadata = request.form.get("metadata", "")
        if metadata:
            # Metadata contains "driver:<name>" - extract for logging
            return metadata.split("driver:", 1)[-1].strip() if "driver:" in metadata else None
    except Exception:
        pass

    return None


def verify_auth_with_service(email, password):
    """
    Call auth-service to verify credentials.

    Args:
        email (str): User email
        password (str): User password

    Returns:
        tuple: (user_data dict, status_code) or (None, error_code) if failed
    """
    try:
        resp = requests.post(
            f"{AUTH_SERVICE_URL}/api/auth/login",
            json={"email": email, "password": password},
            timeout=5
        )

        if resp.status_code == 200:
            return resp.json(), 200
        else:
            return None, resp.status_code

    except requests.exceptions.RequestException as e:
        log.error(f"Auth service error: {e}")
        return None, 503
