"""Shared JSON persistence.

Writes the same ``sessions.json`` / ``sessions_minimal.json`` /
``individual_sessions/<mobile>.json`` trio the Telegram bot maintains, so an
account harvested by either process is immediately usable by the other.

Dashboard-local state (``dashboard_state.json``) holds proxy assignments,
cart/address templates, single-use share links, per-number usage tags and the
incognito flags.
"""
from __future__ import annotations

import json
import os
import secrets
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import config

MINIMAL_KEYS = ("mobile", "token", "sid", "tid", "deviceId", "customerId")

_lock = threading.RLock()
_state_cache: dict[str, Any] | None = None


# ── raw io ───────────────────────────────────────────────────────────────────
def read_json(path: Path, default: Any = None) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError, OSError):
        return default if default is not None else []


def atomic_write(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ── dashboard state (proxy stickiness, login tickets live in memory) ─────────
def state() -> dict[str, Any]:
    global _state_cache
    with _lock:
        if _state_cache is None:
            data = read_json(config.STATE_FILE, {})
            if not isinstance(data, dict):
                data = {}
            data.setdefault("assignments", {})
            _state_cache = data
        return _state_cache


def save_state() -> None:
    with _lock:
        data = state()
        data["updated"] = time.time()
        atomic_write(config.STATE_FILE, data)


# ── sessions ─────────────────────────────────────────────────────────────────
def _full() -> list[dict]:
    data = read_json(config.SESSIONS_FULL, [])
    return [r for r in data if isinstance(r, dict)] if isinstance(data, list) else []


def _minimal() -> list[dict]:
    data = read_json(config.SESSIONS_MINIMAL, [])
    return [r for r in data if isinstance(r, dict)] if isinstance(data, list) else []


def mask_token(token: str) -> str:
    token = str(token or "")
    if len(token) <= 8:
        return token
    return f"{token[:4]}…{token[-4:]}"


def public(record: dict) -> dict:
    """Session view for the UI — token truncated, no raw credentials."""
    out = dict(record)
    out["token_masked"] = mask_token(record.get("token", ""))
    out.pop("token", None)
    out.pop("sid", None)
    out.pop("tid", None)
    out.pop("otp", None)
    out.pop("fingerprint", None)
    mobile = str(record.get("mobile", "")).strip()
    out["mode"] = mode(mobile)
    out["tags"] = tags_for(mobile)
    return out


def list_sessions() -> list[dict]:
    with _lock:
        recs = _full()
    known = {str(r.get("mobile", "")) for r in recs}
    # Minimal-store entries with no full record still deserve a row.
    for r in _minimal():
        mob = str(r.get("mobile", ""))
        if mob and mob not in known:
            recs.append(dict(r))
            known.add(mob)
    recs.sort(key=lambda r: str(r.get("completedAt") or r.get("sessionStatusCheckedAt") or ""),
              reverse=True)
    return recs


def get_session(mobile: str) -> dict | None:
    mobile = str(mobile or "").strip()
    if not mobile:
        return None
    with _lock:
        for r in _full():
            if str(r.get("mobile", "")).strip() == mobile:
                return dict(r)
        for r in _minimal():
            if str(r.get("mobile", "")).strip() == mobile:
                return dict(r)
    return None


def upsert_session(record: dict) -> None:
    """Replace-or-insert by mobile across all three stores."""
    mobile = str(record.get("mobile", "")).strip()
    if not mobile:
        raise ValueError("session record has no mobile")
    with _lock:
        full = _full()
        replaced = False
        for idx, existing in enumerate(full):
            if str(existing.get("mobile", "")).strip() == mobile:
                merged = {**existing, **record}
                full[idx] = merged
                replaced = True
                break
        if not replaced:
            full.append(record)
        atomic_write(config.SESSIONS_FULL, full)

        minimal = _minimal()
        row = {k: record.get(k, "") for k in MINIMAL_KEYS}
        replaced = False
        for idx, existing in enumerate(minimal):
            if str(existing.get("mobile", "")).strip() == mobile:
                minimal[idx] = {**existing, **row}
                replaced = True
                break
        if not replaced:
            minimal.append(row)
        atomic_write(config.SESSIONS_MINIMAL, minimal)

        try:
            config.INDIVIDUAL_DIR.mkdir(parents=True, exist_ok=True)
            atomic_write(config.INDIVIDUAL_DIR / f"{mobile}.json", record)
        except OSError:
            pass


def update_session(mobile: str, fields: dict) -> bool:
    mobile = str(mobile or "").strip()
    if not mobile:
        return False
    with _lock:
        full = _full()
        changed = False
        for record in full:
            if str(record.get("mobile", "")).strip() == mobile:
                record.update(fields)
                changed = True
        if changed:
            atomic_write(config.SESSIONS_FULL, full)

        minimal = _minimal()
        keep = {k: v for k, v in fields.items() if k in MINIMAL_KEYS}
        if keep:
            for record in minimal:
                if str(record.get("mobile", "")).strip() == mobile:
                    record.update(keep)
            atomic_write(config.SESSIONS_MINIMAL, minimal)

        if changed:
            path = config.INDIVIDUAL_DIR / f"{mobile}.json"
            individual = read_json(path, {})
            if isinstance(individual, dict) and individual:
                individual.update(fields)
                try:
                    atomic_write(path, individual)
                except OSError:
                    pass
    return changed


def delete_session(mobile: str) -> bool:
    mobile = str(mobile or "").strip()
    if not mobile:
        return False
    with _lock:
        full = _full()
        keep = [r for r in full if str(r.get("mobile", "")).strip() != mobile]
        removed = len(keep) != len(full)
        if removed:
            atomic_write(config.SESSIONS_FULL, keep)
        minimal = _minimal()
        keep_min = [r for r in minimal if str(r.get("mobile", "")).strip() != mobile]
        if len(keep_min) != len(minimal):
            atomic_write(config.SESSIONS_MINIMAL, keep_min)
            removed = True
        path = config.INDIVIDUAL_DIR / f"{mobile}.json"
        try:
            path.unlink()
            removed = True
        except FileNotFoundError:
            pass
    return removed


def set_status(mobile: str, status: str, extra: dict | None = None) -> None:
    fields = {"sessionStatus": status, "sessionStatusCheckedAt": now_iso()}
    if extra:
        fields.update(extra)
    update_session(mobile, fields)


# ── templates (item lists + address drafts), dashboard-local ────────────────
TEMPLATE_KINDS = ("items", "addresses")


def templates(kind: str = "") -> dict[str, Any]:
    """Saved cart line-sets and address drafts, keyed by name."""
    data = state()
    store = data.get("templates")
    if not isinstance(store, dict):
        store = {}
        data["templates"] = store
    for key in TEMPLATE_KINDS:
        if not isinstance(store.get(key), dict):
            store[key] = {}
    if kind:
        if kind not in TEMPLATE_KINDS:
            raise ValueError(f"unknown template kind: {kind}")
        return dict(store[kind])
    return {key: dict(store[key]) for key in TEMPLATE_KINDS}


def save_template(kind: str, name: str, payload: Any) -> dict:
    if kind not in TEMPLATE_KINDS:
        raise ValueError(f"unknown template kind: {kind}")
    label = str(name or "").strip()[:60]
    if not label:
        raise ValueError("template name is required")
    data = state()
    store = data.setdefault("templates", {})
    store.setdefault(kind, {})[label] = payload
    save_state()
    return {"ok": True, "kind": kind, "name": label, "saved": len(store[kind])}


def delete_template(kind: str, name: str) -> dict:
    if kind not in TEMPLATE_KINDS:
        raise ValueError(f"unknown template kind: {kind}")
    store = state().setdefault("templates", {}).setdefault(kind, {})
    removed = store.pop(str(name or ""), None) is not None
    if removed:
        save_state()
    return {"ok": removed, "kind": kind, "name": name}


# ── usage tags — "1 food used", per number ──────────────────────────────────
TAG_DOMAINS = ("food", "im")


def _tags_store() -> dict[str, Any]:
    store = state().setdefault("tags", {})
    if not isinstance(store, dict):
        store = {}
        state()["tags"] = store
    return store


def tags_for(mobile: str) -> dict[str, Any]:
    """Per-number counters the order history has proven."""
    mobile = str(mobile or "").strip()
    row = _tags_store().get(mobile) if mobile else None
    row = row if isinstance(row, dict) else {}
    out: dict[str, Any] = {key: int(row.get(key) or 0) for key in TAG_DOMAINS}
    out["total"] = sum(out.values())
    out["updated"] = row.get("updated") or ""
    out["labels"] = tag_labels(out)
    return out


def tag_labels(counts: dict[str, Any]) -> list[str]:
    """["1 food", "2 instamart"] — the chip text the UI prints."""
    labels = []
    words = {"food": "food", "im": "instamart"}
    for key in TAG_DOMAINS:
        value = int(counts.get(key) or 0)
        if value:
            labels.append(f"{value} {words[key]}")
    return labels


def tag_set(mobile: str, domain: str, count: int, source: str = "") -> dict[str, Any]:
    """Overwrite one counter. Order history is the source of truth, so the count
    replaces rather than accumulates — a re-load of the same history must not
    double the tag."""
    mobile = str(mobile or "").strip()
    if not mobile:
        raise ValueError("mobile is required")
    if domain not in TAG_DOMAINS:
        raise ValueError(f"unknown tag domain: {domain}")
    with _lock:
        row = _tags_store().setdefault(mobile, {})
        row[domain] = max(0, int(count))
        row["updated"] = now_iso()
        if source:
            row["source"] = source
        save_state()
    return {"ok": True, "mobile": mobile, **tags_for(mobile)}


def tag_bump(mobile: str, domain: str, delta: int = 1, source: str = "") -> dict[str, Any]:
    current = tags_for(mobile).get(domain, 0)
    return tag_set(mobile, domain, current + int(delta), source)


def tags_all() -> dict[str, Any]:
    return {mobile: tags_for(mobile) for mobile in sorted(_tags_store())}


# ── incognito · normal ───────────────────────────────────────────────────────
MODES = ("normal", "incognito")


def mode(mobile: str) -> str:
    mobile = str(mobile or "").strip()
    if not mobile:
        return "normal"
    store = state().get("modes")
    value = store.get(mobile) if isinstance(store, dict) else None
    return value if value in MODES else "normal"


def set_mode(mobile: str, value: str) -> dict[str, Any]:
    mobile = str(mobile or "").strip()
    value = str(value or "").strip().lower()
    if not mobile:
        raise ValueError("mobile is required")
    if value not in MODES:
        raise ValueError(f"mode must be one of {', '.join(MODES)}")
    with _lock:
        modes = state().setdefault("modes", {})
        if value == "normal":
            modes.pop(mobile, None)
        else:
            modes[mobile] = value
        save_state()
    activity("session", mobile, f"mode → {value}")
    return {"ok": True, "mobile": mobile, "mode": mode(mobile)}


# ── share links (single-use, 24 h) ───────────────────────────────────────────
def _shares_store() -> dict[str, Any]:
    store = state().setdefault("shares", {})
    if not isinstance(store, dict):
        store = {}
        state()["shares"] = store
    return store


def _share_state(record: dict) -> str:
    if record.get("used"):
        return "used"
    try:
        if float(record.get("expires") or 0) <= time.time():
            return "expired"
    except (TypeError, ValueError):
        return "expired"
    return "live"


def share_create(payload: dict, ttl: int | None = None, created_by: str = "") -> dict[str, Any]:
    """Mint a one-shot token. Payload is whatever the caller wants carried —
    address, coordinates, cart lines, group link."""
    if not isinstance(payload, dict):
        raise ValueError("payload must be an object")
    ttl = int(ttl or config.SHARE_TTL)
    if ttl < 60:
        raise ValueError("ttl must be at least 60 seconds")
    token = secrets.token_urlsafe(9)
    now = time.time()
    record = {
        "token": token,
        "created": now,
        "created_iso": now_iso(),
        "expires": now + ttl,
        "expires_iso": datetime.fromtimestamp(now + ttl, timezone.utc)
                               .strftime("%Y-%m-%dT%H:%M:%SZ"),
        "used": 0,
        "used_at": None,
        "consumed_by": "",
        "by": str(created_by or ""),
        "payload": payload,
    }
    with _lock:
        store = _shares_store()
        # sweep old spent/expired tokens so the file cannot grow forever
        cutoff = time.time() - config.SHARE_SWEEP
        for key in [k for k, v in store.items()
                    if isinstance(v, dict) and float(v.get("created") or 0) < cutoff]:
            store.pop(key, None)
        store[token] = record
        save_state()
    return {**share_public(token, record), "ttl": ttl}


def share_public(token: str, record: dict | None = None) -> dict[str, Any]:
    record = record if isinstance(record, dict) else _shares_store().get(token) or {}
    state_name = _share_state(record)
    return {"ok": state_name == "live", "token": token, "state": state_name,
            "created": record.get("created_iso"), "expires": record.get("expires_iso"),
            "used_at": record.get("used_at"), "used": bool(record.get("used")),
            "by": record.get("by", ""),
            "payload": record.get("payload") if state_name == "live" else None}


def share_get(token: str) -> dict[str, Any]:
    token = str(token or "").strip()
    record = _shares_store().get(token)
    if not isinstance(record, dict):
        raise KeyError("share link not found")
    out = share_public(token, record)
    out["error"] = {"used": "this link has already been claimed",
                    "expired": "this link expired",
                    "live": None}[out["state"]]
    return out


def share_consume(token: str, consumer: str = "") -> dict[str, Any]:
    """Hand the payload over exactly once, then burn the token."""
    token = str(token or "").strip()
    with _lock:
        record = _shares_store().get(token)
        if not isinstance(record, dict):
            raise KeyError("share link not found")
        state_name = _share_state(record)
        if state_name != "live":
            return {"ok": False, "token": token, "state": state_name,
                    "error": ("this link has already been claimed" if state_name == "used"
                              else "this link expired")}
        record["used"] = 1
        record["used_at"] = now_iso()
        record["consumed_by"] = str(consumer or "")[:80]
        save_state()
        return {"ok": True, "token": token, "state": "used",
                "used_at": record["used_at"], "payload": record.get("payload") or {},
                "created": record.get("created_iso"), "by": record.get("by", "")}


def shares_all() -> list[dict[str, Any]]:
    rows = [share_public(token, rec) for token, rec in _shares_store().items()
            if isinstance(rec, dict)]
    rows.sort(key=lambda r: str(r.get("created") or ""), reverse=True)
    return rows


# ── activity log (dashboard-local, line-delimited so it never grows a rewrite) ─
def activity(kind: str, mobile: str = "", detail: Any = "") -> None:
    # Incognito: nothing about this number touches the activity log.
    if mobile and mode(mobile) == "incognito":
        return
    entry = {"ts": now_iso(), "kind": kind, "mobile": mobile, "detail": detail}
    try:
        config.ACTIVITY_FILE.parent.mkdir(parents=True, exist_ok=True)
        with config.ACTIVITY_FILE.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError:
        pass


def recent_activity(limit: int = 60) -> list[dict]:
    path = config.ACTIVITY_FILE
    if not path.exists():
        return []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()[-limit:]
    except OSError:
        return []
    out = []
    for line in reversed(lines):
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except ValueError:
            continue
    return out
