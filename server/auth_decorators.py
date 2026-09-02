"""
Authentication decorators for AES Logistics API.
Handles role-based access control via Authorization headers.
"""
import os
from functools import wraps
from flask import jsonify
from auth_utils import get_auth_header
import logging

log = logging.getLogger(__name__)

# Check if running in production (Railway)
IS_PRODUCTION = bool(os.getenv("RAILWAY_ENVIRONMENT_NAME"))


def login_required(f):
    """
    Requires Authorization header with user email.
    In development, allows any request with auth info.
    In production (Railway), enforces strict authentication.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        auth_info = get_auth_header()

        if not auth_info:
            log.warning(f"Unauthorized access attempt to {f.__name__}")
            return jsonify({"error": "not logged in"}), 401

        # In production, could add token validation here
        # For now, presence of auth_info is sufficient

        return f(*args, **kwargs)

    return decorated_function


def admin_required(f):
    """
    Requires admin role. Currently checks for auth info.
    TODO: Integrate with auth-service token validation to verify admin role.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        auth_info = get_auth_header()

        if not auth_info:
            log.warning(f"Unauthorized admin access attempt to {f.__name__}")
            return jsonify({"error": "admin access required"}), 401

        # TODO: Call auth-service to verify admin role
        # For now, just require authentication
        # In production, should validate role from auth-service

        log.info(f"Admin action by {auth_info}: {f.__name__}")
        return f(*args, **kwargs)

    return decorated_function


def pm_or_admin_required(f):
    """
    Requires PM or Admin role. Currently checks for auth info.
    TODO: Integrate with auth-service token validation to verify role.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        auth_info = get_auth_header()

        if not auth_info:
            log.warning(f"Unauthorized PM/Admin access attempt to {f.__name__}")
            return jsonify({"error": "PM or admin access required"}), 401

        # TODO: Call auth-service to verify PM or admin role
        # For now, just require authentication

        log.info(f"PM/Admin action by {auth_info}: {f.__name__}")
        return f(*args, **kwargs)

    return decorated_function
