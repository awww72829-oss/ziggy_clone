"""Proxy pool with sticky per-account egress.

One session always leaves through one IP: the assignment is derived from the
mobile number and persisted, so a restart or a pool reload does not teleport a
logged-in account to a different country mid-session.

ProxyRise-style LLS proxies (host containing ``resfix-in-nnid``) hand back an
``X-PR-LLS`` header that pins the sticky session; ``resolve()`` locks it once
per proxy and reuses the token until it expires.
"""
from __future__ import annotations

import hashlib
import threading
import time

import requests
import urllib3

from . import config, storage

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

LLS_MARKER = "resfix-in-nnid"
LLS_TTL = 1800
_SCHEMES = ("http://", "https://", "socks4://", "socks4a://", "socks5://", "socks5h://")


def _normalise(raw: str) -> str:
    line = (raw or "").strip()
    if not line:
        return ""
    if not line.startswith(_SCHEMES):
        line = "http://" + line
    return line


def _label(proxy: str) -> str:
    return (proxy.split("@")[-1] if "@" in proxy else proxy)[:48]


class ProxyPool:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._pool: list[str] = []
        self._health: dict[str, dict] = {}
        self._lls: dict[str, tuple[str, float]] = {}
        self._loaded_at = 0.0
        self.reload()

    # ── pool ─────────────────────────────────────────────────────────────────
    def reload(self) -> list[str]:
        lines: list[str] = []
        try:
            for raw in config.PROXIES_FILE.read_text(encoding="utf-8").splitlines():
                if raw.strip().startswith("#"):
                    continue
                entry = _normalise(raw)
                if entry and entry not in lines:
                    lines.append(entry)
        except FileNotFoundError:
            pass
        with self._lock:
            self._pool = lines
            self._health = {}
            self._loaded_at = time.time()
        return list(lines)

    def all(self) -> list[str]:
        with self._lock:
            return list(self._pool)

    def __len__(self) -> int:
        return len(self._pool)

    # ── assignment ───────────────────────────────────────────────────────────
    def _deterministic(self, mobile: str) -> str:
        digest = hashlib.sha256(f"swiggy-egress:{mobile}".encode()).hexdigest()
        return self._pool[int(digest[:8], 16) % len(self._pool)]

    def pick(self, mobile: str) -> str | None:
        """Stable proxy for one account. None means direct connection."""
        if not self._pool:
            return None
        mobile = str(mobile or "")
        state = storage.state()
        assignments = state.setdefault("assignments", {})
        stored = assignments.get(mobile)
        if stored and stored in self._pool:
            return stored
        chosen = self._deterministic(mobile)
        assignments[mobile] = chosen
        storage.save_state()
        return chosen

    def assign(self, mobile: str, proxy: str) -> str:
        state = storage.state()
        state.setdefault("assignments", {})[mobile] = proxy
        storage.save_state()
        return proxy

    def release(self, mobile: str) -> None:
        state = storage.state()
        if state.get("assignments", {}).pop(mobile, None) is not None:
            storage.save_state()

    def usage(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for proxy in storage.state().get("assignments", {}).values():
            counts[proxy] = counts.get(proxy, 0) + 1
        return counts

    # ── LLS locking ──────────────────────────────────────────────────────────
    def resolve(self, proxy: str | None) -> str | None:
        """Return a proxy string that is safe to hand to requests.Session."""
        if not proxy or LLS_MARKER not in proxy:
            return proxy
        with self._lock:
            cached = self._lls.get(proxy)
            if cached and cached[1] > time.time():
                return cached[0]
        locked = proxy
        try:
            session = requests.Session()
            session.verify = False
            session.proxies = {"http": proxy, "https": proxy}
            response = session.get("https://httpbin.org/ip", timeout=12)
            token = response.headers.get("X-PR-LLS") or response.headers.get("x-pr-lls")
            if token:
                scheme, _, rest = proxy.partition("://")
                userinfo, _, host = rest.rpartition("@")
                user = userinfo.split(":", 1)[0]
                password = userinfo.split(":", 1)[1] if ":" in userinfo else ""
                locked_user = f"{user}-{token}" if LLS_MARKER in user else f"resfix-in-nnid-{token}"
                locked = f"{scheme}://{locked_user}:{password}@{host}"
        except Exception:
            locked = proxy
        with self._lock:
            self._lls[proxy] = (locked, time.time() + LLS_TTL)
        return locked

    # ── health ───────────────────────────────────────────────────────────────
    def health(self, proxy: str, force: bool = False) -> dict:
        now = time.time()
        if not force:
            cached = self._health.get(proxy)
            if cached and cached.get("checked_at", 0) > now - config.PROXY_HEALTH_TTL:
                return cached
        result = self._probe(proxy)
        with self._lock:
            self._health[proxy] = result
        return result

    @staticmethod
    def _probe(proxy: str) -> dict:
        started = time.time()
        try:
            session = requests.Session()
            session.verify = False
            session.proxies = {"http": proxy, "https": proxy}
            response = session.get("https://api.ipify.org?format=json", timeout=15)
            latency = int((time.time() - started) * 1000)
            if response.status_code == 200:
                return {"ok": True, "ip": response.json().get("ip", "?"),
                        "latency_ms": latency, "checked_at": time.time()}
            return {"ok": False, "error": f"HTTP {response.status_code}",
                    "latency_ms": latency, "checked_at": time.time()}
        except Exception as exc:
            return {"ok": False, "error": str(exc)[:120], "latency_ms": None,
                    "checked_at": time.time()}

    def snapshot(self, force: bool = False) -> list[dict]:
        usage = self.usage()
        out = []
        for proxy in self.all():
            health = self.health(proxy, force=force)
            out.append({
                "proxy": proxy,
                "label": _label(proxy),
                "lls": LLS_MARKER in proxy,
                "accounts": usage.get(proxy, 0),
                **{k: v for k, v in health.items() if k != "checked_at"},
                "checked_at": health.get("checked_at"),
            })
        return out
