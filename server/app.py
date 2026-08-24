#!/usr/bin/env python3
"""
AES Logistics - Auth-Service Integration Test Server
 
Minimal Flask app that tests auth-service integration.
No static file serving - just API endpoints.
"""
 
import os
import sys
import logging
from datetime import datetime
from functools import wraps
 
from dotenv import load_dotenv
from flask import Flask, jsonify, session, request
import requests
 
load_dotenv()
 
# ===== Configuration =====
AUTH_SERVICE_URL = os.environ.get("AUTH_SERVICE_URL", "http://localhost:5000")
FLASK_SECRET_KEY = os.environ.get("FLASK_SECRET_KEY", "dev-key-change-in-production")
 
# ===== Flask Setup =====
app = Flask(__name__)
 
app.secret_key = FLASK_SECRET_KEY
app.config.update(
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SECURE=True,
    PERMANENT_SESSION_LIFETIME=60 * 60 * 24 * 30,  # 30 days
)
 
# ===== Logging =====
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("aes_logistics")
 
# ===== Auth Decorators =====
def login_required(f):
    """Decorator to require login - checks local session."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "user_id" not in session:
            return jsonify({"error": "not logged in"}), 401
        return f(*args, **kwargs)
    return decorated_function
 
 
def admin_required(f):
    """Decorator to require admin role."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "user_id" not in session:
            return jsonify({"error": "not logged in"}), 401
        if session.get("role") != "admin":
            return jsonify({"error": "admin access required"}), 403
        return f(*args, **kwargs)
    return decorated_function
 
 
def pm_or_admin_required(f):
    """Decorator to require PM or admin role."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "user_id" not in session:
            return jsonify({"error": "not logged in"}), 401
        if session.get("role") not in ("pm", "admin"):
            return jsonify({"error": "pm or admin access required"}), 403
        return f(*args, **kwargs)
    return decorated_function
 
 
# ===== Root Routes (API Only - No Static File Serving) =====
@app.route("/")
def root():
    """Root endpoint - returns API info."""
    return jsonify({
        "service": "AES Logistics API",
        "version": "1.0.0-minimal",
        "auth_service": AUTH_SERVICE_URL,
        "endpoints": {
            "auth": {
                "login": "POST /api/auth/login",
                "logout": "POST /api/auth/logout",
                "me": "GET /api/auth/me"
            },
            "admin": {
                "register": "POST /api/auth/admin/register_user",
                "users": "GET /api/auth/admin/users"
            }
        }
    })
 
 
# ===== Auth Endpoints (Proxy to Auth-Service) =====
 
@app.route("/api/auth/login", methods=["POST"])
def api_login():
    """Login - proxy to auth-service and establish local session."""
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""
 
    if not email or not password:
        return jsonify({"error": "Email and password required"}), 400
 
    try:
        # Call auth-service
        resp = requests.post(
            f"{AUTH_SERVICE_URL}/api/auth/login",
            json={"email": email, "password": password},
            timeout=5
        )
 
        if resp.status_code != 200:
            return jsonify({"error": "Invalid email or password"}), 401
 
        user_data = resp.json()
 
        # Establish local session
        session["user_id"] = user_data.get("user_id")
        session["email"] = user_data.get("email")
        session["name"] = user_data.get("name")
        session["role"] = user_data.get("role")
        session.permanent = True
 
        log.info(f"User logged in: {email} ({user_data.get('role')})")
 
        return jsonify({
            "user_id": user_data.get("user_id"),
            "email": user_data.get("email"),
            "name": user_data.get("name"),
            "role": user_data.get("role")
        }), 200
 
    except requests.exceptions.RequestException as e:
        log.error(f"Auth service error: {e}")
        return jsonify({"error": "Authentication service unavailable"}), 503
 
 
@app.route("/api/auth/logout", methods=["POST"])
def api_logout():
    """Logout - clear local session."""
    email = session.get("email", "unknown")
    session.clear()
    log.info(f"User logged out: {email}")
    return jsonify({"status": "ok"})
 
 
@app.route("/api/auth/me", methods=["GET"])
def api_me():
    """Get current user from local session."""
    if "user_id" not in session:
        return jsonify({"error": "not logged in"}), 401
 
    return jsonify({
        "user_id": session.get("user_id"),
        "email": session.get("email"),
        "name": session.get("name"),
        "role": session.get("role")
    })
 
 
@app.route("/api/auth/admin/register_user", methods=["POST"])
@pm_or_admin_required
def api_admin_register_user():
    """Register new user (Admin/PM only)."""
    data = request.get_json(silent=True) or {}
 
    try:
        # Call auth-service to register user
        resp = requests.post(
            f"{AUTH_SERVICE_URL}/api/auth/register",
            json={
                "name": data.get("name"),
                "email": data.get("email"),
                "password": data.get("password"),
                "role": data.get("role", "driver")
            },
            timeout=5
        )
 
        if resp.status_code not in (200, 201):
            error_data = resp.json() if resp.text else {}
            return jsonify({"error": error_data.get("error", "Failed to register user")}), resp.status_code
 
        user_data = resp.json()
        log.info(f"User registered: {data.get('email')}")
        return jsonify(user_data), resp.status_code
 
    except requests.exceptions.RequestException as e:
        log.error(f"Auth service error: {e}")
        return jsonify({"error": "Authentication service unavailable"}), 503
 
 
@app.route("/api/auth/admin/users", methods=["GET"])
@pm_or_admin_required
def api_admin_list_users():
    """List all users (PM or Admin only)."""
    try:
        resp = requests.get(
            f"{AUTH_SERVICE_URL}/api/auth/users",
            timeout=5
        )
 
        if resp.status_code != 200:
            return jsonify({"error": "Failed to fetch users"}), resp.status_code
 
        data = resp.json()
        return jsonify({"users": data.get("users", [])})
 
    except requests.exceptions.RequestException as e:
        log.error(f"Auth service error: {e}")
        return jsonify({"error": "Authentication service unavailable"}), 503
 
 
# ===== Health Check =====
@app.route("/api/health", methods=["GET"])
def health():
    """Health check endpoint."""
    return jsonify({"status": "ok", "time": datetime.now().isoformat()})
 
 
# ===== Error Handlers =====
@app.errorhandler(404)
def not_found(error):
    """Handle 404 errors."""
    return jsonify({"error": "Not found"}), 404
 
 
@app.errorhandler(500)
def server_error(error):
    """Handle 500 errors."""
    log.error(f"Server error: {error}")
    return jsonify({"error": "Internal server error"}), 500
 
 
# ===== Startup =====
if __name__ == "__main__":
    log.info(f"Starting AES Logistics Auth-Service Test Server...")
    log.info(f"Auth Service URL: {AUTH_SERVICE_URL}")
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
 
