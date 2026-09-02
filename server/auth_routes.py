"""
Authentication routes for AES Logistics API.
Endpoints: /api/auth/login, /api/auth/logout, /api/auth/me
All authentication is proxied to auth-service on Railway.
"""
from flask import Blueprint, request, jsonify
from auth_utils import get_auth_header, verify_auth_with_service
import logging

log = logging.getLogger(__name__)

# Create Blueprint for auth routes
auth_bp = Blueprint("auth", __name__, url_prefix="/api/auth")


@auth_bp.route("/login", methods=["POST"])
def login():
    """
    Login endpoint - proxy to auth-service.
    Client handles session locally, not server.

    Request JSON:
        {
            "email": "user@example.com",
            "password": "password123"
        }

    Returns:
        {
            "user_id": "...",
            "email": "user@example.com",
            "name": "User Name",
            "role": "driver" | "pm" | "admin"
        }
    """
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""

    if not email or not password:
        return jsonify({"error": "Email and password required"}), 400

    # Verify credentials with auth-service
    user_data, status = verify_auth_with_service(email, password)

    if status != 200:
        return jsonify({"error": "Invalid email or password"}), 401

    log.info(f"User authenticated via auth-service: {email} ({user_data.get('role')})")

    # Return auth-service response directly
    # Client is responsible for storing auth info locally
    return jsonify(user_data), 200


@auth_bp.route("/logout", methods=["POST"])
def logout():
    """
    Logout endpoint - proxy to auth-service.
    Client clears local auth, server has nothing to clear.
    (This server does not manage sessions)

    Returns:
        {"status": "ok"}
    """
    auth_info = get_auth_header()
    if auth_info:
        log.info(f"User logged out: {auth_info}")
    return jsonify({"status": "ok"})


@auth_bp.route("/me", methods=["GET"])
def get_me():
    """
    Get current user info from Authorization header.
    Client provides auth info, not server.

    Returns:
        {"email": "user@example.com"} or 401 if not authenticated
    """
    auth_info = get_auth_header()
    if not auth_info:
        return jsonify({"error": "not logged in"}), 401

    return jsonify({"email": auth_info}), 200
