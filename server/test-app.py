from flask import Flask, jsonify
import os

# Add these imports one at a time to find which one breaks
import io
import json
import logging
import re
import secrets
import shutil
import sys
import uuid
from datetime import datetime
from functools import wraps

from dotenv import load_dotenv
import requests

# Start with these
import emailer
import inventory
import inventory_report
import maps
import qr_ticket
import scheduling
import sms
import ticket_render

app = Flask(__name__)

@app.route("/api/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"}), 200

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)