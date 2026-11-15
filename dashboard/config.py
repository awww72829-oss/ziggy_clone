"""Dashboard configuration — paths shared with the bot, plus runtime tuning."""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DASH_DIR = Path(__file__).resolve().parent
STATIC_DIR = DASH_DIR / "static"

# Files owned by the farm — same schema, read and written in place.
SESSIONS_FULL = ROOT / "sessions.json"
SESSIONS_MINIMAL = ROOT / "sessions_minimal.json"
PROXIES_FILE = ROOT / "proxies.txt"
INDIVIDUAL_DIR = ROOT / "individual_sessions"

# Dashboard-owned state.
STATE_FILE = DASH_DIR / "dashboard_state.json"
ACTIVITY_FILE = DASH_DIR / "dashboard_activity.jsonl"

BIND_HOST = os.getenv("DASHBOARD_HOST", "127.0.0.1").strip() or "127.0.0.1"
BIND_PORT = int(os.getenv("DASHBOARD_PORT", "8899"))
# When set, every /api request needs X-Dashboard-Token (or ?token= for the page load).
ACCESS_TOKEN = os.getenv("DASHBOARD_TOKEN", "").strip()

REQUEST_TIMEOUT = int(os.getenv("DASHBOARD_TIMEOUT", "20"))
CHECK_WORKERS = 8
TICKET_TTL = 600  # seconds an OTP login stays verifiable

# Share links: single-use, 24 h. Swiggy has no share-token API — the link is a
# dashboard token that carries the address/geo/item payload; the receiver opens
# /s/<token>, the server hands over the payload once and burns it.
SHARE_TTL = int(os.getenv("DASHBOARD_SHARE_TTL", str(24 * 60 * 60)))
SHARE_SWEEP = 7 * 24 * 60 * 60  # drop spent tokens after a week
SHARE_BASE_URL = os.getenv("DASHBOARD_SHARE_BASE", "").strip()  # e.g. https://box.example
# Instamart filler search: cheap line items so a cart can clear a minimum.
FILLER_QUERIES = ("1 rupee", "under 20", "sachet", "candy", "chocolate")
FILLER_MAX_PRICE = float(os.getenv("DASHBOARD_FILLER_MAX", "1"))

# Pacing between mutating calls on one account. Keeps a session's traffic
# looking like one person on one phone instead of a script.
PACE_MIN = 0.35
PACE_MAX = 1.10

LIVENESS_TTL = 900  # reuse a LIVE result for this long
PROXY_HEALTH_TTL = 600
MAX_BODY = 1 << 20
