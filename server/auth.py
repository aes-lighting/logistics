"""
auth.py

Login for the AES Logistics app. Two kinds of accounts:

  - Driver / warehouse staff: self-service. The first time a name is used,
    whatever code they type (a 6-digit PIN or a word — no format is
    enforced beyond a minimum length) becomes that name's code from then on.
    Nothing is pre-provisioned; there's no separate "sign up" step.

  - Admin: a single fixed account. Credentials come from environment
    variables (ADMIN_EMAIL / ADMIN_PASSWORD in .env), never hardcoded here
    and never stored in server_config.json. On every server start, if those
    env vars are set, the stored admin record is (re)synced to match them —
    so rotating the admin password later is just: edit .env, restart the
    server.

Everything is hashed at rest with werkzeug's password hashing (PBKDF2) —
plaintext codes/passwords are never written to disk.

Storage: a small JSON file (auth_store.json) next to this module. Fine for a
handful of driver accounts; if this grows into dozens of staff, swap it for
a real database.
"""

import json
import logging
import os
from datetime import datetime
from functools import wraps

from flask import session, jsonify
from werkzeug.security import generate_password_hash, check_password_hash

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
AUTH_STORE_PATH = os.path.join(BASE_DIR, "auth_store.json")
MIN_CODE_LENGTH = 4

log = logging.getLogger("aes_logistics.auth")


def _load_store():
    if not os.path.isfile(AUTH_STORE_PATH):
        return {"drivers": {}, "admin": None, "pms": {}}
    with open(AUTH_STORE_PATH, "r") as f:
        store = json.load(f)
    store.setdefault("pms", {})
    return store


def _save_store(store):
    with open(AUTH_STORE_PATH, "w") as f:
        json.dump(store, f, indent=2)


def seed_admin_from_env():
    """
    Called once at server startup. If ADMIN_EMAIL and ADMIN_PASSWORD are set
    in the environment, (re)writes the admin record to match — this is what
    makes changing the admin password later just an .env edit + restart.
    """
    email = os.environ.get("ADMIN_EMAIL")
    password = os.environ.get("ADMIN_PASSWORD")

    if not email or not password:
        log.warning("ADMIN_EMAIL/ADMIN_PASSWORD not set in environment — no admin account configured.")
        return

    store = _load_store()
    store["admin"] = {
        "email": email.strip().lower(),
        "password_hash": generate_password_hash(password),
        "updated_at": datetime.now().isoformat(),
    }
    _save_store(store)
    log.info(f"Admin account synced from environment for {email}.")


def driver_login(name, code):
    """
    Returns (status_code, response_dict).
    First use of a name registers it with whatever code is given.
    """
    name = (name or "").strip()
    code = (code or "").strip()

    if not name:
        return 400, {"error": "Enter a name."}
    if len(code) < MIN_CODE_LENGTH:
        return 400, {"error": f"Code must be at least {MIN_CODE_LENGTH} characters (a 6-digit PIN or a word both work)."}

    store = _load_store()
    name_key = name.lower()

    if name_key not in store["drivers"]:
        store["drivers"][name_key] = {
            "display_name": name,
            "code_hash": generate_password_hash(code),
            "created_at": datetime.now().isoformat(),
        }
        _save_store(store)
        session["role"] = "driver"
        session["name"] = name
        log.info(f"New driver account created: {name}")
        return 200, {"status": "ok", "role": "driver", "name": name, "created": True}

    record = store["drivers"][name_key]
    if not check_password_hash(record["code_hash"], code):
        return 401, {"error": "Incorrect code for that name."}

    session["role"] = "driver"
    session["name"] = record["display_name"]
    return 200, {"status": "ok", "role": "driver", "name": record["display_name"], "created": False}


def admin_login(email, password):
    email = (email or "").strip().lower()
    password = password or ""

    store = _load_store()
    admin = store.get("admin")

    if not admin or admin["email"] != email or not check_password_hash(admin["password_hash"], password):
        return 401, {"error": "Incorrect email or password."}

    session["role"] = "admin"
    session["email"] = admin["email"]
    return 200, {"status": "ok", "role": "admin", "email": admin["email"]}


def register_pm(name, email, password):
    """Admin-provisioned PM account."""
    name = (name or "").strip()
    email = (email or "").strip().lower()

    if not name or not email:
        return 400, {"error": "Enter a name and email."}
    if len(password or "") < MIN_CODE_LENGTH:
        return 400, {"error": f"Password must be at least {MIN_CODE_LENGTH} characters."}

    store = _load_store()
    if email in store["pms"]:
        return 409, {"error": f"'{email}' already has a PM account."}

    store["pms"][email] = {
        "display_name": name,
        "email": email,
        "password_hash": generate_password_hash(password),
        "created_at": datetime.now().isoformat(),
    }
    _save_store(store)
    log.info(f"PM account registered: {name} <{email}>")
    return 200, {"status": "ok", "name": name, "email": email}


def pm_login(email, password):
    email = (email or "").strip().lower()
    password = password or ""

    store = _load_store()
    record = store["pms"].get(email)
    if not record or not check_password_hash(record["password_hash"], password):
        return 401, {"error": "Incorrect email or password."}

    session["role"] = "pm"
    session["email"] = record["email"]
    session["name"] = record["display_name"]
    return 200, {"status": "ok", "role": "pm", "email": record["email"], "name": record["display_name"]}


def list_pms():
    store = _load_store()
    return [
        {"name": rec["display_name"], "email": rec["email"], "created_at": rec.get("created_at")}
        for rec in store["pms"].values()
    ]


def register_driver(name, code):
    """
    Admin-initiated registration. Unlike driver_login's auto-register-on-first-use,
    this fails if the name already exists — use reset_driver_code for that instead,
    so an admin can't accidentally overwrite an existing driver's code by mistyping
    a name here.
    """
    name = (name or "").strip()
    code = (code or "").strip()

    if not name:
        return 400, {"error": "Enter a name."}
    if len(code) < MIN_CODE_LENGTH:
        return 400, {"error": f"Code must be at least {MIN_CODE_LENGTH} characters (a 6-digit PIN or a word both work)."}

    store = _load_store()
    name_key = name.lower()

    if name_key in store["drivers"]:
        return 409, {"error": f"'{name}' already has an account. Use Reset Code instead if you need to change their PIN."}

    store["drivers"][name_key] = {
        "display_name": name,
        "code_hash": generate_password_hash(code),
        "created_at": datetime.now().isoformat(),
    }
    _save_store(store)
    log.info(f"Driver account registered by admin: {name}")
    return 200, {"status": "ok", "name": name}


def reset_driver_code(name, new_code):
    name = (name or "").strip()
    new_code = (new_code or "").strip()

    if len(new_code) < MIN_CODE_LENGTH:
        return 400, {"error": f"Code must be at least {MIN_CODE_LENGTH} characters."}

    store = _load_store()
    name_key = name.lower()
    if name_key not in store["drivers"]:
        return 404, {"error": f"No driver account found for '{name}'."}

    store["drivers"][name_key]["code_hash"] = generate_password_hash(new_code)
    store["drivers"][name_key]["updated_at"] = datetime.now().isoformat()
    _save_store(store)
    return 200, {"status": "ok", "name": store["drivers"][name_key]["display_name"]}


def list_drivers():
    store = _load_store()
    return [
        {"name": rec["display_name"], "created_at": rec.get("created_at")}
        for rec in store["drivers"].values()
    ]


def current_session():
    role = session.get("role")
    if role == "driver":
        return {"role": "driver", "name": session.get("name")}
    if role == "admin":
        return {"role": "admin", "email": session.get("email")}
    if role == "pm":
        return {"role": "pm", "email": session.get("email"), "name": session.get("name")}
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
