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

def call_auth_service(path, method="GET", data=None, auth_header=None):
    """Call auth-service endpoint"""
    url = f"{AUTH_SERVICE_URL}{path}"
    headers = {"Content-Type": "application/json"}
    if auth_header:
        headers["Authorization"] = auth_header
    
    try:
        log.info(f"Calling auth-service: {method} {url} with auth_header={bool(auth_header)}")
        if method == "GET":
            resp = requests.get(url, headers=headers, timeout=5)
        elif method == "POST":
            resp = requests.post(url, json=data, headers=headers, timeout=5)
        elif method == "DELETE":
            resp = requests.delete(url, headers=headers, timeout=5)
        else:
            return {"error": "Invalid method"}, 400
        
        log.info(f"Auth-service returned status {resp.status_code}")
        
        # Try to parse JSON response
        try:
            response_data = resp.json()
        except ValueError:
            # Response is not JSON - log what we got
            log.error(f"Non-JSON response from auth-service: status={resp.status_code}, body={resp.text[:500]}")
            return {"error": f"Invalid response from auth-service: {resp.text[:100]}"}, resp.status_code
        
        return response_data, resp.status_code
        
    except requests.exceptions.Timeout:
        log.error("Auth-service request timed out")
        return {"error": "Auth service timeout"}, 503
    except requests.exceptions.ConnectionError as e:
        log.error(f"Could not connect to auth-service: {e}")
        return {"error": f"Could not connect to auth service: {str(e)}"}, 503
    except Exception as e:
        log.error(f"Auth service error: {e}", exc_info=True)
        return {"error": str(e)}, 500