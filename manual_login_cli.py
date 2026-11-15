#!/usr/bin/env python3
"""
Swiggy Manual Login CLI
Fast terminal-based interactive login tool:
  - Input mobile number
  - Request SMS OTP
  - Input received OTP
  - Extract tokens & save directly to sessions.json
"""

import hashlib
import json
import random
import re
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
import warnings

warnings.filterwarnings("ignore")

try:
    import requests
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
except ImportError:
    print("Please install requests & rich: pip3 install requests rich")
    sys.exit(1)

console = Console()

SESSIONS_FULL = Path("sessions.json")
SESSIONS_MINIMAL = Path("sessions_minimal.json")
PROXIES_FILE = Path("proxies.txt")

SMS_OTP_URL = "https://profile.swiggy.com/api/v3/app/sms_otp"
VERIFY_URL = "https://profile.swiggy.com/api/v3/app/login/verify"

ANDROID_DEVICES = [
    {"model": "Pixel 8", "manufacturer": "Google", "os": "14", "sdk": "34"},
    {"model": "Pixel 7", "manufacturer": "Google", "os": "13", "sdk": "33"},
    {"model": "SM-S911B", "manufacturer": "samsung", "os": "14", "sdk": "34"},
    {"model": "SM-A546B", "manufacturer": "samsung", "os": "13", "sdk": "33"},
    {"model": "M2101K6P", "manufacturer": "Xiaomi", "os": "13", "sdk": "33"},
    {"model": "Redmi Note 12", "manufacturer": "Xiaomi", "os": "13", "sdk": "33"},
]

def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

def generate_fingerprint() -> dict:
    seed = f"{time.time_ns()}-{uuid.uuid4()}-{random.random()}"
    h = hashlib.sha256(seed.encode()).hexdigest()
    dev = random.choice(ANDROID_DEVICES)
    vc = random.randint(1680, 1780)
    av = f"4.{random.randint(100, 115)}.{random.randint(0, 25)}"
    return {
        "deviceId": str(uuid.uuid4()),
        "swuid": h[16:32],
        "androidId": h[:16],
        "installationId": str(uuid.uuid4()),
        "model": dev["model"],
        "manufacturer": dev["manufacturer"],
        "osVersion": dev["os"],
        "sdk": dev["sdk"],
        "versionCode": str(vc),
        "appVersion": av,
        "plVersion": str(random.randint(120, 145)),
        "userAgent": f"Swiggy-Android/{vc} (Android {dev['os']}; {dev['model']})",
        "fingerprintHash": h[:16],
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

def load_json(p: Path) -> list:
    if not p.exists():
        return []
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return []

def atomic_save(path: Path, data: list):
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)

def save_session(full_rec: dict):
    minimal = {
        "mobile": full_rec.get("mobile", ""),
        "token": full_rec.get("token", ""),
        "sid": full_rec.get("sid", ""),
        "tid": full_rec.get("tid", ""),
        "deviceId": full_rec.get("deviceId", ""),
        "customerId": full_rec.get("customerId", "")
    }
    fl = [s for s in load_json(SESSIONS_FULL) if str(s.get("mobile", "")).strip() != full_rec["mobile"]]
    fl.insert(0, full_rec)
    atomic_save(SESSIONS_FULL, fl)

    ml = [s for s in load_json(SESSIONS_MINIMAL) if str(s.get("mobile", "")).strip() != minimal["mobile"]]
    ml.insert(0, minimal)
    atomic_save(SESSIONS_MINIMAL, ml)

def main():
    console.print(Panel.fit("[bold cyan]Swiggy Manual Login & Session Extractor[/bold cyan]\\n[dim]Direct IP / Proxy Support[/dim]", border_style="cyan"))

    # Proxy selection
    console.print("\\n[bold]1. Network Connection:[/bold]")
    console.print("  [1] Direct IP (No proxy - your current network, Recommended)")
    console.print("  [2] Use proxy from proxies.txt")
    console.print("  [3] Custom proxy (socks5h://... or http://...)")
    choice = console.input("[yellow]Select [1/2/3] (default 1): [/yellow]").strip() or "1"

    sess = requests.Session()
    if choice == "2":
        if PROXIES_FILE.exists():
            for line in PROXIES_FILE.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line and not line.startswith("#"):
                    sess.proxies = {"http": line, "https": line}
                    console.print(f"[green]✓ Loaded proxy: {line.split('@')[-1]}[/green]")
                    break
        else:
            console.print("[red]proxies.txt not found. Using direct connection.[/red]")
    elif choice == "3":
        c_px = console.input("[yellow]Enter proxy URL: [/yellow]").strip()
        if c_px:
            sess.proxies = {"http": c_px, "https": c_px}
            console.print(f"[green]✓ Set proxy: {c_px.split('@')[-1]}[/green]")

    # Mobile Input
    phone_raw = console.input("\\n[bold yellow]Enter 10-digit Indian Mobile Number: [/bold yellow]").strip()
    m = re.search(r"(?:(?:\+|0{0,2})91[\s.\-]?)?([6-9]\d{9})\b", phone_raw)
    if not m:
        console.print("[bold red]Invalid phone number![/bold red]")
        sys.exit(1)
    phone = m.group(1)

    fp = generate_fingerprint()
    headers = build_headers(fp)
    console.print(f"[dim]Device: {fp['manufacturer']} {fp['model']} (Android {fp['osVersion']})[/dim]")
    console.print(f"[cyan]Sending SMS OTP to +91 {phone}...[/cyan]")

    try:
        r = sess.get(f"{SMS_OTP_URL}?mobile={phone}", headers=headers, timeout=15)
        res_json = r.json() if r.content else {}
    except Exception as e:
        console.print(f"[bold red]Request failed: {e}[/bold red]")
        sys.exit(1)

    data_inner = res_json.get("data") if isinstance(res_json.get("data"), dict) else {}
    tid = res_json.get("tid") or data_inner.get("tid")
    sid = res_json.get("sid") or data_inner.get("sid")
    status_msg = res_json.get("statusMessage") or res_json.get("message") or f"HTTP {r.status_code}"

    if r.status_code != 200 or (res_json.get("statusCode") not in (0, 1, None) and not tid):
        console.print(f"[bold red]Failed to send OTP: {status_msg}[/bold red]")
        console.print(f"[dim]{res_json}[/dim]")
        sys.exit(1)

    console.print(f"[bold green]✓ OTP sent successfully! ({status_msg})[/bold green]")
    console.print(f"[dim]sid: {sid} | tid: {tid[:20]}...[/dim]\\n")

    # OTP Input
    otp = console.input("[bold yellow]Enter the received OTP: [/bold yellow]").strip()
    if not otp:
        console.print("[bold red]OTP cannot be empty[/bold red]")
        sys.exit(1)

    console.print("[cyan]Verifying OTP with Swiggy...[/cyan]")
    req_headers = {**headers, "sid": sid or "", "Tid": tid or ""}
    payload = {
        "cloningSignalsData": {
            "appFilesDirPathInvalid": 0, "developerModeEnabled": 0,
            "deviceModelVmos": 0, "emulatorStatus": 0,
            "packageName": "in.swiggy.android", "workProfileEnabled": 0,
        },
        "otp": otp,
    }

    try:
        vr = sess.post(f"{VERIFY_URL}?otp_source=Sms-automatic", headers=req_headers, json=payload, timeout=15)
        vdata = vr.json() if vr.content else {}
    except Exception as e:
        console.print(f"[bold red]Verify call failed: {e}[/bold red]")
        sys.exit(1)

    vinner = vdata.get("data") if isinstance(vdata.get("data"), dict) else {}
    token = vinner.get("token") or vdata.get("token") or vinner.get("accessToken") or ""
    cid = str(vinner.get("customerId") or vinner.get("userid") or vinner.get("userId") or "")

    if vr.status_code != 200 or not token:
        errmsg = vdata.get("statusMessage") or vdata.get("message") or f"HTTP {vr.status_code}"
        console.print(f"[bold red]Verification failed: {errmsg}[/bold red]")
        console.print(f"[dim]{vdata}[/dim]")
        sys.exit(1)

    full_record = {
        "sessionId": uuid.uuid4().hex,
        "mobile": phone,
        "token": token,
        "sid": sid,
        "tid": tid,
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
        "customerId": cid,
        "otp": otp,
        "sourceDevice": "manual_login_cli",
        "fingerprint": fp,
        "completedAt": now_iso()
    }
    save_session(full_record)

    t = Table(title="🎉 Swiggy Login Successful", border_style="green")
    t.add_column("Field", style="cyan")
    t.add_column("Value", style="white")
    t.add_row("Mobile", f"+91 {phone}")
    t.add_row("Customer ID", cid or "N/A")
    t.add_row("Token", token)
    t.add_row("Session ID (sid)", sid or "N/A")
    t.add_row("Token ID (tid)", (tid or "N/A")[:40] + "...")
    t.add_row("Saved In", "sessions.json & sessions_minimal.json")
    console.print(t)

if __name__ == "__main__":
    main()

