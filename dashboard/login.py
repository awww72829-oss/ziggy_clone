"""Manual phone + OTP login.

Builds the identical session record the Firebase farm writes, so both processes
share one ``sessions.json`` with no schema drift. The send and the verify reuse
one ``requests.Session`` on one sticky proxy, because Swiggy binds the pending
login to the cookies set when the OTP went out.
"""
from __future__ import annotations

import hashlib
import random
import threading
import time
import uuid
from datetime import datetime, timezone
from urllib.parse import urlparse

import requests
import urllib3

from . import config, storage
from .proxies import ProxyPool

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

SMS_OTP_URL = "https://profile.swiggy.com/api/v3/app/sms_otp"
VERIFY_URL = "https://profile.swiggy.com/api/v3/app/login/verify"

ANDROID_DEVICES = [
    {"model": "Pixel 7", "manufacturer": "Google", "os": "13", "sdk": "33"},
    {"model": "Pixel 6a", "manufacturer": "Google", "os": "14", "sdk": "34"},
    {"model": "Pixel 8", "manufacturer": "Google", "os": "14", "sdk": "34"},
    {"model": "SM-S911B", "manufacturer": "samsung", "os": "14", "sdk": "34"},
    {"model": "SM-A546B", "manufacturer": "samsung", "os": "13", "sdk": "33"},
    {"model": "SM-G991B", "manufacturer": "samsung", "os": "14", "sdk": "34"},
    {"model": "V2109", "manufacturer": "vivo", "os": "13", "sdk": "33"},
    {"model": "CPH2451", "manufacturer": "OPPO", "os": "13", "sdk": "33"},
    {"model": "RMX3630", "manufacturer": "realme", "os": "13", "sdk": "33"},
    {"model": "M2101K6P", "manufacturer": "Xiaomi", "os": "13", "sdk": "33"},
    {"model": "ONEPLUS A6000", "manufacturer": "OnePlus", "os": "13", "sdk": "33"},
    {"model": "Redmi Note 12", "manufacturer": "Xiaomi", "os": "13", "sdk": "33"},
]

_tickets: dict[str, dict] = {}
_lock = threading.Lock()


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def normalise_mobile(raw: str) -> str:
    digits = "".join(ch for ch in str(raw or "") if ch.isdigit())
    if digits.startswith("91") and len(digits) == 12:
        digits = digits[2:]
    if digits.startswith("0") and len(digits) == 11:
        digits = digits[1:]
    return digits if len(digits) == 10 and digits[0] in "6789" else ""


def generate_fingerprint() -> dict:
    seed = f"{time.time_ns()}-{uuid.uuid4()}-{random.random()}"
    digest = hashlib.sha256(seed.encode()).hexdigest()
    device = random.choice(ANDROID_DEVICES)
    version_code = random.randint(1680, 1780)
    app_version = f"4.{random.randint(100, 115)}.{random.randint(0, 25)}"
    return {
        "deviceId": str(uuid.uuid4()),
        "swuid": digest[16:32],
        "androidId": digest[:16],
        "installationId": str(uuid.uuid4()),
        "model": device["model"],
        "manufacturer": device["manufacturer"],
        "osVersion": device["os"],
        "sdk": device["sdk"],
        "versionCode": str(version_code),
        "appVersion": app_version,
        "plVersion": str(random.randint(120, 145)),
        "userAgent": f"Swiggy-Android/{version_code} (Android {device['os']}; {device['model']})",
        "fingerprintHash": digest[:16],
    }


def build_headers(fp: dict) -> dict:
    return {
        "Accept": "application/json; charset=utf-8",
        "app-version": fp["appVersion"],
        "category": "food",
        "deviceId": fp["deviceId"],
        "swuid": fp["swuid"],
        "androidId": fp["androidId"],
        "os-version": fp["osVersion"],
        "pl-version": fp["plVersion"],
        "User-Agent": fp["userAgent"],
        "version-code": fp["versionCode"],
        "x-channel": "swiggy",
        "X-Device-Id": fp["deviceId"],
        "platform": "android",
        "Content-Type": "application/json; charset=utf-8",
    }


def _transport(proxy: str | None) -> requests.Session:
    session = requests.Session()
    session.verify = False
    if proxy:
        session.proxies = {"http": proxy, "https": proxy}
    return session


def _prune() -> None:
    cutoff = time.time() - config.TICKET_TTL
    for key in [k for k, v in _tickets.items() if v.get("created", 0) < cutoff]:
        _tickets.pop(key, None)


def _message(payload: dict, fallback: str) -> str:
    inner = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    return (payload.get("statusMessage") or payload.get("message")
            or inner.get("statusMessage") or inner.get("message") or fallback)


def send_otp(mobile: str, pool: ProxyPool) -> dict:
    """Ask Swiggy for an SMS OTP. Returns a ticket id the verify step needs."""
    phone = normalise_mobile(mobile)
    if not phone:
        return {"ok": False, "error": "invalid mobile — 10 digits starting 6-9"}

    _prune()
    proxy = pool.resolve(pool.pick(phone))
    fp = generate_fingerprint()
    headers = build_headers(fp)
    session = _transport(proxy)
    try:
        response = session.get(f"{SMS_OTP_URL}?mobile={phone}",
                               headers=headers, timeout=config.REQUEST_TIMEOUT)
    except requests.exceptions.ProxyError:
        proxy = None
        session = _transport(None)
        try:
            response = session.get(f"{SMS_OTP_URL}?mobile={phone}",
                                   headers=headers, timeout=config.REQUEST_TIMEOUT)
        except Exception as exc:
            return {"ok": False, "error": f"network: {exc}"[:160]}
    except Exception as exc:
        return {"ok": False, "error": f"network: {exc}"[:160]}

    try:
        payload = response.json() if response.content else {}
    except ValueError:
        payload = {"_body": (response.text or "")[:200]}

    if response.status_code == 403:
        storage.activity("login", phone, "OTP send blocked (403)")
        return {"ok": False, "error": "HTTP 403 from Swiggy — every exit IP is hot, rotate proxies"}

    inner = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    tid = str(payload.get("tid") or inner.get("tid") or "")
    sid = str(payload.get("sid") or inner.get("sid") or "")
    ok = response.status_code == 200 and bool(tid)
    if not ok:
        message = _message(payload, f"HTTP {response.status_code}")
        storage.activity("login", phone, f"OTP send failed: {message[:120]}")
        return {"ok": False, "error": message[:160], "status": response.status_code}

    ticket = uuid.uuid4().hex
    with _lock:
        _tickets[ticket] = {
            "mobile": phone, "fp": fp, "headers": headers, "session": session,
            "tid": tid, "sid": sid, "proxy": proxy, "created": time.time(),
        }
    storage.activity("login", phone, "OTP sent")
    return {"ok": True, "ticket": ticket, "mobile": phone, "tid": tid[:12] + "…",
            "proxy_used": bool(proxy)}


def verify_otp(ticket: str, otp: str) -> dict:
    """Finish the login and persist a farm-compatible session record."""
    with _lock:
        entry = _tickets.get(ticket)
    if not entry:
        return {"ok": False, "error": "login ticket expired — send the OTP again"}
    otp = "".join(ch for ch in str(otp or "") if ch.isdigit())
    if not 4 <= len(otp) <= 8:
        return {"ok": False, "error": "OTP must be 4-8 digits"}

    headers = {**entry["headers"], "sid": entry["sid"] or "", "Tid": entry["tid"] or ""}
    body = {
        "cloningSignalsData": {
            "appFilesDirPathInvalid": 0, "developerModeEnabled": 0,
            "deviceModelVmos": 0, "emulatorStatus": 0,
            "packageName": "in.swiggy.android", "workProfileEnabled": 0,
        },
        "otp": otp,
    }
    try:
        response = entry["session"].post(f"{VERIFY_URL}?otp_source=Sms-automatic",
                                         headers=headers, json=body,
                                         timeout=config.REQUEST_TIMEOUT)
    except Exception as exc:
        return {"ok": False, "error": f"network: {exc}"[:160]}

    try:
        payload = response.json() if response.content else {}
    except ValueError:
        payload = {"_body": (response.text or "")[:200]}

    if response.status_code == 403:
        storage.activity("login", entry["mobile"], "OTP verify blocked (403)")
        return {"ok": False, "error": "HTTP 403 on verify — rotate the proxy and retry"}

    inner = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    token = str(inner.get("token") or payload.get("token")
                or inner.get("accessToken") or "")
    unregistered = response.status_code == 200 and (
        inner.get("registered") is False
        or (payload.get("statusCode") == 0 and not token))
    if unregistered and not token:
        token = "UNREGISTERED_ACCOUNT"
    if response.status_code != 200 or not token:
        message = _message(payload, f"HTTP {response.status_code}")
        storage.activity("login", entry["mobile"], f"OTP verify failed: {message[:120]}")
        return {"ok": False, "error": message[:160], "status": response.status_code}

    fp = entry["fp"]
    record = {
        "sessionId": uuid.uuid4().hex,
        "mobile": entry["mobile"],
        "token": token,
        "sid": str(payload.get("sid") or entry["sid"] or ""),
        "tid": str(payload.get("tid") or entry["tid"] or ""),
        "deviceId": fp["deviceId"],
        "androidId": fp["androidId"],
        "swuid": fp["swuid"],
        "model": fp["model"],
        "manufacturer": fp["manufacturer"],
        "osVersion": fp["osVersion"],
        "appVersion": fp["appVersion"],
        "versionCode": fp["versionCode"],
        "userAgent": fp["userAgent"],
        "fingerprintHash": fp["fingerprintHash"],
        "customerId": str(inner.get("customerId") or inner.get("userid")
                          or inner.get("userId") or ""),
        "otp": otp,
        "sourceDevice": "dashboard-manual",
        "sourcePanelHost": "manual-login",
        "fingerprint": fp,
        "sessionStatus": "LIVE",
        "sessionStatusCheckedAt": now_iso(),
        "completedAt": now_iso(),
    }
    storage.upsert_session(record)
    with _lock:
        _tickets.pop(ticket, None)
    storage.activity("login", entry["mobile"],
                     f"session saved (customerId={record['customerId'] or 'new'})")
    return {"ok": True, "session": storage.public(record),
            "unregistered": unregistered}
