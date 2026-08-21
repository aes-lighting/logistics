"""
auth.py

One unified login for everyone: an @aes-energy.com email plus a single
shared password (default "aes", overridable via the SHARED_PASSWORD
environment variable). There's no per-person PIN anymore — every account
is pre-registered (name, email, role) via Admin Tools, and everyone signs
in the same way regardless of whether they're a driver, warehouse worker,
project manager, or admin.

SECURITY NOTE — worth reading, not just boilerplate: a single password
shared by every account is inherently weak. Anyone who knows it can log in
as anyone else, including an admin. That's a deliberate simplification for
easy pilot testing on your own server, not something to carry into a real
production rollout without tightening — swap in per-user passwords or an
SSO provider before this is used somewhere the stakes are higher.

Storage: a small JSON file (auth_store.json) next to this module. Fine for
a handful of accounts; if this grows into dozens+ of staff, swap it for a
real database.
"""

import json
import logging
import os
import re
from datetime import datetime
from functools import wraps

from flask import session, jsonify
from werkzeug.security import generate_password_hash, check_password_hash

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
AUTH_STORE_PATH = os.path.join(BASE_DIR, "auth_store.json")

VALID_ROLES = ("driver", "pm", "admin")
EMAIL_DOMAIN = "@aes-energy.com"

log = logging.getLogger("aes_logistics.auth")


def _shared_password():
    return os.environ.get("SHARED_PASSWORD", "aes")


def _load_store():
    if not os.path.isfile(AUTH_STORE_PATH):
        return {"users": {}}
    with open(AUTH_STORE_PATH, "r") as f:
        store = json.load(f)
    store.setdefault("users", {})
    return store


def _save_store(store):
    with open(AUTH_STORE_PATH, "w") as f:
        json.dump(store, f, indent=2)


def seed_admin_from_env():
    """
    Called once at server startup. If ADMIN_EMAIL is set, makes sure that
    email is registered with role "admin" so there's always at least one
    way in to start registering everyone else. Uses the shared password
    like every other account — see the module-level security note.
    """
    email = os.environ.get("ADMIN_EMAIL")
    if not email:
        log.warning("ADMIN_EMAIL not set in environment — no admin account seeded.")
        return

    email = email.strip().lower()
    store = _load_store()
    if email not in store["users"]:
        store["users"][email] = {
            "email": email,
            "name": "Admin",
            "role": "admin",
            "password_hash": generate_password_hash(_shared_password()),
            "created_at": datetime.now().isoformat(),
        }
        _save_store(store)
        log.info(f"Seeded initial admin account for {email}.")
    else:
        log.info(f"Admin account for {email} already exists.")


def register_user(name, email, role):
    """Admin/PM-initiated registration. Every account uses the shared password."""
    name = (name or "").strip()
    email = (email or "").strip().lower()
    role = (role or "").strip().lower()

    if not name:
        return 400, {"error": "Enter a name."}
    if not email:
        return 400, {"error": "Enter an email."}
    if not email.endswith(EMAIL_DOMAIN):
        return 400, {"error": f"Email must end in {EMAIL_DOMAIN}."}
    if role not in VALID_ROLES:
        return 400, {"error": f"Role must be one of: {', '.join(VALID_ROLES)}."}

    store = _load_store()
    if email in store["users"]:
        return 409, {"error": f"'{email}' already has an account."}

    store["users"][email] = {
        "email": email,
        "name": name,
        "role": role,
        "password_hash": generate_password_hash(_shared_password()),
        "created_at": datetime.now().isoformat(),
    }
    _save_store(store)
    log.info(f"Registered {role} account: {name} <{email}>")
    return 200, {"status": "ok", "name": name, "email": email, "role": role}


def login(email, password):
    """
    Returns (status_code, response_dict). Every registered account uses the
    same shared password — see the module-level security note.
    """
    email = (email or "").strip().lower()
    password = password or ""

    store = _load_store()
    record = store["users"].get(email)
    if not record or not check_password_hash(record["password_hash"], password):
        return 401, {"error": "Incorrect email or password."}

    session["role"] = record["role"]
    session["email"] = record["email"]
    session["name"] = record["name"]
    return 200, {"status": "ok", "role": record["role"], "email": record["email"], "name": record["name"]}


def list_users():
    store = _load_store()
    return sorted(
        [
            {"name": rec["name"], "email": rec["email"], "role": rec["role"], "created_at": rec.get("created_at")}
            for rec in store["users"].values()
        ],
        key=lambda u: u["name"].lower(),
    )


def current_session():
    role = session.get("role")
    if role in VALID_ROLES:
        return {"role": role, "email": session.get("email"), "name": session.get("name")}
    return None


def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not current_session():
            return jsonify({"error": "Login required."}), 401
        return f(*args, **kwargs)
    return wrapper


def admin_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if session.get("role") != "admin":
            return jsonify({"error": "Admin login required."}), 403
        return f(*args, **kwargs)
    return wrapper


def pm_or_admin_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if session.get("role") not in ("pm", "admin"):
            return jsonify({"error": "PM or admin login required."}), 403
        return f(*args, **kwargs)
    return wrapper
