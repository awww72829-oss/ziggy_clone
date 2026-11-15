#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
account_ops.py — per-account Swiggy operations for the control panel.

Every call takes one harvested session record (mobile, token, sid, tid,
deviceId, customerId, appVersion, versionCode, ...) and talks to Swiggy on
that account's behalf, through the same proxy pool the harvester uses.

Two transports are used, matching the reference:

  • Native Android surface (token headers: tid/sid/token/deviceId/platform)
      profile.swiggy.com   — profile, order history, delete, logout
      chkout.swiggy.com    — Swiggy Money balance / eligibility

  • MCP JSON-RPC surface (Authorization: Bearer <token>)
      mcp.swiggy.com/im    — Instamart grocery
      mcp.swiggy.com/food  — Food delivery

The MCP surface is the clean checkout path: the server owns the
place→pay→confirm chain, so checkout() is a single tool call.

Endpoints and argument keys come from SWIGGY_APIS.txt. Response shapes are
parsed defensively; anything unrecognised is returned raw under "raw".
"""

from __future__ import annotations

import json
import base64
import time
from typing import Any
from urllib.parse import urlencode

import requests

PROFILE_BASE = "https://profile.swiggy.com"
CHKOUT_BASE  = "https://chkout.swiggy.com"
WEB_BASE     = "https://www.swiggy.com"
MCP_IM       = "https://mcp.swiggy.com/im"
MCP_FOOD     = "https://mcp.swiggy.com/food"
PAYMENTS_BASE = "https://payments.swiggy.com"

DEFAULT_UA   = "Swiggy-Android/1782 (Android 14; Pixel 6)"
WEB_UA       = ("Mozilla/5.0 (Linux; Android 14; Pixel 6) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36")

# position hint every native call must carry; overridable per account record
DEFAULT_LATITUDE  = "12.9716"   # Bangalore centre
DEFAULT_LONGITUDE = "77.5946"

_MCP_ID_LOCK = None
_MCP_ID = 0


def _next_id() -> int:
    global _MCP_ID
    _MCP_ID += 1
    return _MCP_ID


def _jwt_claim(token: str, key: str) -> Any:
    """Read one claim out of a JWT payload without verifying the signature.

    Used only for identity fields the harvested record already holds a valid
    session for — never for anything security-bearing.
    """
    try:
        payload = str(token).split(".")[1]
        payload += "=" * (-len(payload) % 4)
        return json.loads(base64.urlsafe_b64decode(payload)).get(key)
    except Exception:
        return None


def _money(v: Any) -> str:
    try:
        return f"₹{float(v):,.2f}"
    except (TypeError, ValueError):
        return str(v) if v is not None else "?"


class Account:
    """One Swiggy account, bound to a harvested session record."""

    def __init__(self, rec: dict, proxy: str | None = None, timeout: int = 20):
        self.rec        = dict(rec or {})
        self.mobile     = str(self.rec.get("mobile", "")).strip()
        self.token      = str(self.rec.get("token", "") or "")
        self.sid        = str(self.rec.get("sid", "") or "")
        self.tid        = str(self.rec.get("tid", "") or "")
        self.device_id  = str(self.rec.get("deviceId", "") or "")
        self.customer_id = str(self.rec.get("customerId", "") or "")
        if not self.customer_id:
            # Harvested records often carry an empty customerId; the tid JWT is
            # minted per login and always carries user_id. The shared-cart v1
            # endpoints key on it and hard-fail ("User Id is not provided")
            # without it.
            claim = _jwt_claim(self.rec.get("tid", "") or "", "user_id")
            if claim:
                self.customer_id = str(claim)
        self.swuid      = str(self.rec.get("swuid", "") or "")
        self.android_id = str(self.rec.get("androidId", "") or "")
        self.app_ver    = str(self.rec.get("appVersion", "4.120.0") or "4.120.0")
        self.ver_code   = str(self.rec.get("versionCode", "1782") or "1782")
        self.os_ver     = str(self.rec.get("osVersion", "14") or "14")
        self.model      = str(self.rec.get("model", "Pixel 6") or "Pixel 6")
        self.manufacturer = str(self.rec.get("manufacturer", "Google") or "Google")
        self.user_agent = str(self.rec.get("userAgent", DEFAULT_UA) or DEFAULT_UA)
        # profile.swiggy.com rejects native calls without a position hint
        # ("missing required header: latitude"). Per-account wins, then the
        # record, then the configured default.
        self.latitude  = str(self.rec.get("latitude") or DEFAULT_LATITUDE)
        self.longitude = str(self.rec.get("longitude") or DEFAULT_LONGITUDE)
        self.proxy      = proxy
        self.timeout    = timeout

    # ── transport ────────────────────────────────────────────────────────────
    def _session(self) -> requests.Session:
        s = requests.Session()
        s.verify = False
        if self.proxy:
            s.proxies = {"http": self.proxy, "https": self.proxy}
        return s

    def has_token(self) -> bool:
        return bool(self.token) and self.token != "UNREGISTERED_ACCOUNT"

    def _native_headers(self) -> dict:
        h = {
            "Accept":       "application/json",
            "Content-Type": "application/json; charset=utf-8",
            "tid":          self.tid,
            "sid":          self.sid,
            "token":        self.token,
            "deviceId":     self.device_id,
            "platform":     "Android",
            "app-version":  self.app_ver,
            "version-code": self.ver_code,
            "os-version":   self.os_ver,
            "User-Agent":   self.user_agent,
            "manufacturer": self.manufacturer,
            "model-name":   self.model,
            "latitude":     self.latitude,
            "longitude":    self.longitude,
        }
        return {k: v for k, v in h.items() if v}

    def _web_headers(self) -> dict:
        h = {
            "Accept":       "application/json",
            "Content-Type": "application/json",
            "User-Agent":   WEB_UA,
            "Origin":       WEB_BASE,
            "Referer":      WEB_BASE + "/",
            "tid":          self.tid,
            "sid":          self.sid,
            "token":        self.token,
            "deviceId":     self.device_id,
            "platform":     "web",
            "app-version":  self.app_ver,
            "version-code": self.ver_code,
            "latitude":     self.latitude,
            "longitude":    self.longitude,
        }
        return {k: v for k, v in h.items() if v}

    @staticmethod
    def _pack(r: requests.Response) -> dict:
        try:
            data = r.json() if r.content else {}
        except Exception:
            data = {"_text": (r.text or "")[:2000]}
        return {"ok": 200 <= r.status_code < 300, "status": r.status_code, "data": data}

    def _get(self, url: str, headers: dict, params: dict | None = None) -> dict:
        try:
            r = self._session().get(url, headers=headers, params=params, timeout=self.timeout)
            return self._pack(r)
        except Exception as e:
            return {"ok": False, "status": 0, "error": str(e)[:200], "data": {}}

    def _post(self, url: str, headers: dict, body: Any = None) -> dict:
        try:
            r = self._session().post(url, headers=headers, json=body, timeout=self.timeout)
            return self._pack(r)
        except Exception as e:
            return {"ok": False, "status": 0, "error": str(e)[:200], "data": {}}

    def _patch(self, url: str, headers: dict, body: Any = None) -> dict:
        try:
            r = self._session().patch(url, headers=headers, json=body, timeout=self.timeout)
            return self._pack(r)
        except Exception as e:
            return {"ok": False, "status": 0, "error": str(e)[:200], "data": {}}

    def _delete(self, url: str, headers: dict, body: Any = None) -> dict:
        try:
            r = self._session().delete(url, headers=headers, json=body, timeout=self.timeout)
            return self._pack(r)
        except Exception as e:
            return {"ok": False, "status": 0, "error": str(e)[:200], "data": {}}

    # ── MCP JSON-RPC ─────────────────────────────────────────────────────────
    def _mcp(self, domain: str, tool: str, args: dict | None = None) -> dict:
        if not self.has_token():
            return {"ok": False, "status": 0, "error": "no token", "data": {}}
        url = MCP_IM if domain == "im" else MCP_FOOD
        body = {
            "jsonrpc": "2.0",
            "id":      _next_id(),
            "method":  "tools/call",
            "params":  {"name": tool, "arguments": args or {}},
        }
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type":  "application/json",
            "Accept":        "application/json, text/event-stream",
            "User-Agent":    self.user_agent,
            "tid":           self.tid,
            "sid":           self.sid,
            "deviceId":      self.device_id,
            "latitude":      self.latitude,
            "longitude":     self.longitude,
        }
        headers = {k: v for k, v in headers.items() if v}
        try:
            r = self._session().post(url, headers=headers, json=body, timeout=self.timeout)
        except Exception as e:
            return {"ok": False, "status": 0, "error": str(e)[:200], "data": {}}
        return self._unpack_mcp(r)

    @staticmethod
    def _unpack_mcp(r: requests.Response) -> dict:
        ct = (r.headers.get("content-type") or "").lower()
        obj = None
        if "event-stream" in ct:
            for line in (r.text or "").splitlines():
                line = line.strip()
                if not line.startswith("data:"):
                    continue
                chunk = line[5:].strip()
                if not chunk or chunk == "[DONE]":
                    continue
                try:
                    obj = json.loads(chunk)
                except Exception:
                    continue
        else:
            try:
                obj = r.json() if r.content else {}
            except Exception:
                return {"ok": False, "status": r.status_code,
                        "error": (r.text or "")[:200], "data": {}}

        if not isinstance(obj, dict):
            return {"ok": False, "status": r.status_code, "error": "bad mcp payload", "data": {}}
        if obj.get("error"):
            err = obj["error"]
            msg = err.get("message") if isinstance(err, dict) else str(err)
            return {"ok": False, "status": r.status_code, "error": msg, "data": obj,
                    "raw": obj}

        result = obj.get("result") or {}
        is_error = bool(result.get("isError"))
        inner = None
        # structuredContent is the machine-readable payload; the text blocks
        # are prose written for a chat model and are lossy for extraction.
        if isinstance(result.get("structuredContent"), (dict, list)):
            inner = result["structuredContent"]
        for c in (result.get("content") or []):
            if inner is not None:
                break
            if isinstance(c, dict) and c.get("type") == "text":
                t = c.get("text") or ""
                try:
                    inner = json.loads(t)
                except Exception:
                    # Successful tool output is a JSON document with a prose
                    # advisory appended ("avoid restating what the widget
                    # shows…"). Parse the leading object, keep the rest.
                    try:
                        inner, _end = json.JSONDecoder().raw_decode(t.lstrip())
                    except Exception:
                        inner = t
        if inner is None:
            inner = result if result else obj
        err = inner.get("error") if isinstance(inner, dict) else None
        if isinstance(err, dict):
            err = err.get("message") or err.get("code") or str(err)
        return {"ok": not is_error and 200 <= r.status_code < 300,
                "status": r.status_code,
                "error": err if is_error else None,
                "data": inner, "raw": obj}

    # ── reads ────────────────────────────────────────────────────────────────
    def alive(self) -> str:
        """LIVE / EXPIRED / ERROR — cheap profile probe."""
        if not self.has_token():
            return "EXPIRED"
        r = self._get(f"{PROFILE_BASE}/api/v3/user/profile",
                      self._native_headers(), {"silentSession": "false"})
        if r.get("status") in (401, 403):
            return "EXPIRED"
        d = r.get("data") or {}
        if isinstance(d, dict) and d.get("statusCode") == 999:
            return "EXPIRED"
        if r.get("ok"):
            return "LIVE"
        return "ERROR"

    def profile(self) -> dict:
        r = self._get(f"{PROFILE_BASE}/api/v4/user/profile",
                      self._native_headers(),
                      {"silentSession": "false", "optionalKeys": ""})
        if not r.get("ok") or not isinstance(r.get("data"), dict):
            return r
        d = r["data"]
        inner = d.get("data") if isinstance(d.get("data"), dict) else d
        r["profile"] = inner
        for key in ("customerId", "userId", "userid", "mobile", "name", "email"):
            if inner.get(key) not in (None, ""):
                r[key] = inner.get(key)
        return r

    def wallet(self) -> dict:
        r = self._get(f"{CHKOUT_BASE}/payment/presentation/v1/swiggypay/getbalance",
                      self._native_headers())
        d = r.get("data") or {}
        inner = d.get("data") if isinstance(d.get("data"), dict) else d
        pres = (inner.get("balancePresenter") or {}) if isinstance(inner, dict) else {}
        avail = pres.get("available")
        if avail is None and isinstance(inner, dict):
            avail = inner.get("available")
        r["available"] = avail
        r["available_fmt"] = _money(avail) if avail is not None else None
        return r

    def wallet_eligibility(self) -> dict:
        return self._get(f"{CHKOUT_BASE}/payment/add-money/v1/order/transaction/eligibility",
                         self._native_headers())

    def orders(self, count: int = 10, order_type: str = "DASH", domain: str = "im",
               active_only: bool = False, address_id: str = "") -> dict:
        args = {"count": int(count), "orderType": order_type}
        if active_only:
            args["activeOnly"] = True
        if domain == "food":
            # the food transport has no get_orders; it exposes get_food_orders
            args.pop("orderType", None)
            args.pop("activeOnly", None)
            if address_id:
                args["addressId"] = address_id
            return self._mcp("food", "get_food_orders", args)
        return self._mcp("im", "get_orders", args)

    def order_history_native(self, count: int = 10, order_type: str = "DASH",
                             from_time: int = 0) -> dict:
        return self._get(f"{PROFILE_BASE}/api/v1/order/history",
                         self._native_headers(),
                         {"order_type": order_type, "count": int(count),
                          "from_time": int(from_time)})

    def order_details(self, order_id: str) -> dict:
        return self._get(f"{PROFILE_BASE}/api/v1/order/getSingleOrder",
                         self._native_headers(), {"order_id": order_id})

    # ── tracking / sharing (web dapi) ────────────────────────────────────────
    # SRC-058/059/061/072: the web session owns the tracking view; the native
    # socket endpoints do not carry the timeline.
    def order_track(self, order_id: str, version: str = "V2") -> dict:
        return self._get(f"{WEB_BASE}/dapi/order/trackV4", self._web_headers(),
                         {"order_id": str(order_id), "type": "full",
                          "version": version, "customer_id": self.customer_id})

    def order_track_v2(self, order_id: str) -> dict:
        return self._get(f"{WEB_BASE}/dapi/order/trackV2/de", self._web_headers(),
                         {"order_id": str(order_id)})

    def order_shareable_link(self, order_id: str) -> dict:
        """Shareable order link — a read-only tracking URL, not a cart share."""
        return self._get(f"{WEB_BASE}/dapi/order/shareableLink", self._web_headers(),
                         {"order_id": str(order_id)})

    def order_share(self, order_id: str) -> dict:
        return self._get(f"{WEB_BASE}/mapi/order/share", self._web_headers(),
                         {"order_id": str(order_id)})

    def addresses(self, domain: str = "food") -> dict:
        return self._mcp(domain, "get_addresses", {})

    def create_address(self, full_address: str, address_line: str, address_line2: str,
                       city: str, postal_code: str, category: str, user_name: str,
                       user_phone: str, locality: str = "", tag: str = "",
                       latitude: float | None = None, longitude: float | None = None,
                       receiver_name: str = "", receiver_phone: str = "",
                       domain: str = "im") -> dict:
        args = {
            "fullAddress":   full_address,
            "addressLine":   address_line,
            "addressLine2":  address_line2 or "",
            "locality":      locality or "",
            "city":          city,
            "postalCode":    postal_code,
            "addressCategory": (category or "OTHER").upper(),
            "addressTag":    tag or "",
            "userName":      user_name,
            "userPhone":     user_phone,
            "receiverName":  receiver_name or "",
            "receiverPhone": receiver_phone or "",
        }
        if latitude is not None and longitude is not None:
            args["latitude"] = float(latitude)
            args["longitude"] = float(longitude)
        return self._mcp(domain, "create_address", args)

    def delete_address(self, address_id: str, domain: str = "im") -> dict:
        return self._mcp(domain, "delete_address", {"addressId": str(address_id)})

    def go_to_items(self, address_id: str, offset: int = 0) -> dict:
        return self._mcp("im", "your_go_to_items",
                         {"addressId": address_id, "offset": int(offset)})

    @staticmethod
    def _v1(result: dict) -> dict:
        """Swiggy v1 answers HTTP 200 with an in-body statusCode.

        0 is success; anything else is a typed failure ("Group cart no longer
        exists", "User Id is not provided"). Fold it into the ok/error pair so
        the UI does not report a 200 as a win.
        """
        body = result.get("data")
        if isinstance(body, dict):
            code = body.get("statusCode")
            codes = body.get("errorCodes") or []
            if (isinstance(code, int) and code != 0) or codes:
                message = body.get("statusMessage") or (codes[0] if codes else f"statusCode {code}")
                return {"ok": False, "status": result.get("status"),
                        "error": str(message)[:200], "data": body}
        return result

    # ── group (shared) cart ──────────────────────────────────────────────────
    # chkout.swiggy.com/api/v1/shared_cart* — native surface, token headers.
    def group_cart_create(self, restaurant_id: str) -> dict:
        return self._v1(self._post(f"{CHKOUT_BASE}/api/v1/shared_cart/create",
                                   self._web_headers(),
                                   {"restaurant_id": str(restaurant_id),
                                    "user_id": self.customer_id}))

    def group_cart_join(self, group_cart_id: str, restaurant_id: str = "") -> dict:
        return self._v1(self._post(f"{CHKOUT_BASE}/api/v1/shared_cart/join",
                                   self._web_headers(),
                                   {"group_cart_id": str(group_cart_id),
                                    "restaurant_id": str(restaurant_id or ""),
                                    "user_id": self.customer_id}))

    def group_cart_info(self, group_cart_id: str) -> dict:
        return self._v1(self._get(f"{CHKOUT_BASE}/api/v1/shared_cart",
                                  self._web_headers(),
                                  {"group_cart_id": str(group_cart_id)}))

    def group_cart_leave(self, group_cart_id: str) -> dict:
        query = urlencode({"group_cart_id": str(group_cart_id),
                           "user_id": self.customer_id})
        return self._v1(self._delete(f"{CHKOUT_BASE}/api/v1/shared_cart?{query}",
                                     self._web_headers(), None))

    def group_cart_update(self, group_cart_id: str, items: list[dict] | None = None,
                          restaurant_id: str = "") -> dict:
        body = {"group_cart_id": str(group_cart_id), "user_id": self.customer_id}
        if restaurant_id:
            body["restaurant_id"] = str(restaurant_id)
        if items is not None:
            body["items"] = items
        return self._v1(self._post(f"{CHKOUT_BASE}/api/v1/shared_cart/update",
                                   self._web_headers(), body))


    def cart(self, domain: str = "im", address_id: str | None = None) -> dict:
        tool = "get_cart" if domain == "im" else "get_food_cart"
        args = {} if domain == "im" else {"addressId": address_id}
        return self._mcp(domain, tool, args)

    # ── cart / ordering (Instamart) ──────────────────────────────────────────
    def search_products(self, query: str, address_id: str) -> dict:
        return self._mcp("im", "search_products",
                         {"query": query, "addressId": address_id})

    def update_cart(self, items: list[dict], address_id: str) -> dict:
        return self._mcp("im", "update_cart",
                         {"selectedAddressId": address_id, "items": items})

    def clear_cart(self) -> dict:
        return self._mcp("im", "clear_cart", {})

    def payment_options(self, address_id: str | None = None, domain: str = "im",
                        cart_amount: float | None = None) -> dict:
        args: dict[str, Any] = {}
        if domain != "im":
            if address_id:
                args["addressId"] = address_id
            if cart_amount is not None:
                args["cartAmount"] = cart_amount
        return self._mcp(domain, "get_payment_options", args)

    def checkout(self, address_id: str, payment_method: str = "Cash",
                 intent_app: str | None = None, generate_qr: bool = False,
                 confirm_duplicate: bool = False) -> dict:
        args = {"addressId": address_id, "paymentMethod": payment_method}
        if intent_app:
            args["intentApp"] = intent_app
        if generate_qr:
            args["generateUPIQR"] = True
        if confirm_duplicate:
            args["confirmDuplicate"] = True
        return self._mcp("im", "checkout", args)

    def check_payment_status(self, paas_id: str, order_id: str | None = None,
                             address_id: str | None = None,
                             cart_id: str | None = None,
                             lat: float | None = None,
                             lng: float | None = None,
                             domain: str = "im",
                             finalize: bool = True) -> dict:
        args: dict[str, Any] = {"paasId": paas_id}
        if order_id:
            args["orderId"] = order_id
        if address_id:
            args["addressId"] = address_id
        if cart_id:
            args["cartId"] = cart_id
        if lat is not None:
            args["lat"] = lat
        if lng is not None:
            args["lng"] = lng
        if domain != "im":
            args["finalize"] = bool(finalize)
        return self._mcp(domain, "check_payment_status", args)

    def confirm_order(self, order_id: str, transaction_id: str | None = None,
                      paas_id: str | None = None, address_id: str | None = None,
                      cart_id: str | None = None,
                      lat: float | None = None, lng: float | None = None,
                      domain: str = "im") -> dict:
        args: dict[str, Any] = {"orderId": order_id}
        for k, v in (("transactionId", transaction_id), ("paasId", paas_id),
                     ("addressId", address_id), ("cartId", cart_id)):
            if v:
                args[k] = v
        if lat is not None:
            args["lat"] = lat
        if lng is not None:
            args["lng"] = lng
        return self._mcp(domain, "confirm_order", args)

    # ── ordering (Food) ──────────────────────────────────────────────────────
    def food_menu(self, restaurant_id: str, address_id: str,
                  lat: float | None = None, lng: float | None = None,
                  page: int = 1, page_size: int = 30) -> dict:
        args: dict[str, Any] = {"restaurantId": restaurant_id,
                                "page": page, "pageSize": page_size}
        if address_id:
            args["addressId"] = address_id
        else:
            args["latitude"] = float(lat if lat is not None else self.latitude)
            args["longitude"] = float(lng if lng is not None else self.longitude)
        return self._mcp("food", "get_restaurant_menu", args)

    def food_cart(self, address_id: str) -> dict:
        return self._mcp("food", "get_food_cart", {"addressId": address_id})

    def search_restaurants(self, query: str, address_id: str = "",
                           lat: float | None = None, lng: float | None = None) -> dict:
        """Find restaurants by name/dish. addressId for signed-in, coords for guest."""
        args: dict[str, Any] = {"query": query}
        if address_id:
            args["addressId"] = address_id
        else:
            args["latitude"] = float(lat if lat is not None else self.latitude)
            args["longitude"] = float(lng if lng is not None else self.longitude)
        return self._mcp("food", "search_restaurants", args)

    def search_menu(self, query: str, address_id: str = "",
                    lat: float | None = None, lng: float | None = None) -> dict:
        """Dish-level search across restaurants."""
        args: dict[str, Any] = {"query": query}
        if address_id:
            args["addressId"] = address_id
        else:
            args["latitude"] = float(lat if lat is not None else self.latitude)
            args["longitude"] = float(lng if lng is not None else self.longitude)
        return self._mcp("food", "search_menu", args)

    def flush_food_cart(self) -> dict:
        return self._mcp("food", "flush_food_cart", {})

    def food_order_details(self, order_id: str) -> dict:
        return self._mcp("food", "get_food_order_details", {"orderId": order_id})

    def track_food_order(self, order_id: str, lat: float, lng: float) -> dict:
        return self._mcp("food", "track_food_order",
                         {"orderId": order_id, "lat": lat, "lng": lng})

    def update_food_cart(self, restaurant_id: str, address_id: str,
                         cart_items: list[dict], restaurant_name: str = "",
                         cutlery: bool = False) -> dict:
        """Set the food cart. cart_items: [{menu_item_id, quantity, variants?}].

        Menu IDs from get_restaurant_menu/search_menu are per-restaurant; sending
        an item from a different restaurant replaces the cart rather than adding.
        """
        clean = []
        for item in cart_items:
            mid = (item.get("menu_item_id") or item.get("menuItemId")
                   or item.get("id"))
            if not mid:
                continue
            row: dict[str, Any] = {"menu_item_id": str(mid),
                                   "quantity": int(item.get("quantity") or 1)}
            for key in ("variants", "variantsV2", "addons"):
                if item.get(key):
                    row[key] = item[key]
            clean.append(row)
        args: dict[str, Any] = {"restaurantId": str(restaurant_id),
                                "addressId": address_id,
                                "cartItems": clean,
                                "latitude": float(self.latitude),
                                "longitude": float(self.longitude),
                                "cutleryOptIn": bool(cutlery)}
        if restaurant_name:
            args["restaurantName"] = restaurant_name
        return self._mcp("food", "update_food_cart", args)

    def place_food_order_mcp(self, address_id: str, payment_method: str = "COD",
                             intent_app: str | None = None,
                             generate_qr: bool = False,
                             note: str = "") -> dict:
        """Open the order. COD returns an orderId ready for confirm_order."""
        args: dict[str, Any] = {"addressId": address_id,
                                "paymentMethod": payment_method}
        if intent_app:
            args["intentApp"] = intent_app
        if generate_qr:
            args["generateUPIQR"] = True
        if note:
            args["noteToRestaurant"] = note
        return self._mcp("food", "place_food_order", args)

    def fetch_food_coupons(self, address_id: str, restaurant_id: str,
                           coupon_code: str = "") -> dict:
        args = {"addressId": address_id, "restaurantId": str(restaurant_id)}
        if coupon_code:
            args["couponCode"] = coupon_code
        return self._mcp("food", "fetch_food_coupons", args)

    def apply_food_coupon(self, address_id: str, coupon_code: str,
                          cart_id: str | int | None = None) -> dict:
        args: dict[str, Any] = {"addressId": address_id,
                                "couponCode": coupon_code}
        if cart_id:
            args["cartId"] = cart_id
        return self._mcp("food", "apply_food_coupon", args)

    def place_food_order(self, **args) -> dict:
        """Raw pass-through for the food transport's place_food_order tool."""
        return self._mcp("food", "place_food_order", args)

    def track_order(self, order_id: str, lat: float, lng: float) -> dict:
        return self._mcp("im", "track_order",
                         {"orderId": order_id, "lat": lat, "lng": lng})

    def tools_list(self, domain: str = "im") -> dict:
        url = MCP_IM if domain == "im" else MCP_FOOD
        body = {"jsonrpc": "2.0", "id": _next_id(), "method": "tools/list", "params": {}}
        headers = {"Authorization": f"Bearer {self.token}",
                   "Content-Type": "application/json",
                   "Accept": "application/json, text/event-stream"}
        try:
            r = self._session().post(url, headers=headers, json=body, timeout=self.timeout)
        except Exception as e:
            return {"ok": False, "error": str(e)[:200], "data": {}}
        return self._unpack_mcp(r)

    # ── wallet / offers / rewards ────────────────────────────────────────────
    def wallet_statement(self, count: int = 20) -> dict:
        return self._get(f"{CHKOUT_BASE}/payment/presentation/v1/swiggypay/statement",
                         self._native_headers(), {"count": int(count)})

    def claim_gift_card(self, code: str, secret: str) -> dict:
        """PATCH /swiggymoney/voucher/claim. statusCode 0 + positive data.value = redeemed."""
        return self._patch(f"{CHKOUT_BASE}/swiggymoney/voucher/claim",
                           self._native_headers(), {"code": code, "secret": secret})

    def payment_offers(self, lat: float, lng: float, restaurant_id: str = "",
                       cart_value: int = 0) -> dict:
        params = {"lat": lat, "lng": lng, "sourcePage": "restaurant",
                  "source_page": "restaurant", "page_type": "restaurant"}
        if restaurant_id:
            params["restaurantId"] = restaurant_id
            params["restaurant_id"] = restaurant_id
        if cart_value:
            params["cart_value"] = int(cart_value)
        return self._get(f"{WEB_BASE}/dapi/offers/payment", self._web_headers(), params)

    def restaurant_offers(self, lat: float, lng: float, restaurant_id: str) -> dict:
        return self._get(f"{WEB_BASE}/dapi/offers/restaurant", self._web_headers(),
                         {"lat": lat, "lng": lng, "restaurantId": restaurant_id})

    def offers_v2(self) -> dict:
        """GET /api/v2/offer — coupon list. Host inferred from the APK dump, not live-verified."""
        return self._get(f"{PROFILE_BASE}/api/v2/offer", self._native_headers())

    def scratch_assign(self, payload: dict | None = None) -> dict:
        return self._post(f"{PROFILE_BASE}/api/v1/scratch-card/assign",
                          self._native_headers(), payload or {})

    def scratch_unlock(self, payload: dict | None = None) -> dict:
        return self._post(f"{PROFILE_BASE}/api/v1/scratch-card/unlock",
                          self._native_headers(), payload or {})

    # ── native cart (dash host, cookie session) ──────────────────────────────
    def native_cart(self) -> dict:
        return self._get("https://dash.swiggy.com/api/v2/view",
                         self._web_headers(), {"cartType": "INSTAMART"})

    def cart_apply_coupon(self, address_id: str, coupon_code: str,
                          cart_items: list[dict] | None = None,
                          restaurant_id: str = "") -> dict:
        return self._post(f"{CHKOUT_BASE}/api/v2/cart/client/applycoupon",
                          self._native_headers(),
                          {"address_id": address_id, "couponCode": coupon_code,
                           "cartItems": cart_items or [], "restaurantId": restaurant_id})

    def cart_remove_coupon(self, address_id: str, coupon_code: str = "") -> dict:
        return self._post(f"{CHKOUT_BASE}/api/v2/cart/client/removecoupon",
                          self._native_headers(),
                          {"address_id": address_id, "couponCode": coupon_code})

    # ── account lifecycle ────────────────────────────────────────────────────
    def delete_check(self) -> dict:
        return self._get(f"{PROFILE_BASE}/api/v1/delete/user_check",
                         self._native_headers())

    def delete_account(self, otp: str) -> dict:
        """Web delete takes an OTP; native delete takes a body of the same shape.
        Tries web first, then native, and reports whichever answered."""
        out = {"web": self._post(f"{WEB_BASE}/mapi/auth/delete/user",
                                 self._web_headers(), {"otp": otp})}
        if not out["web"].get("ok"):
            out["native"] = self._post(f"{PROFILE_BASE}/api/v1/delete/user",
                                       self._native_headers(), {"otp": otp})
        return out

    def logout(self) -> dict:
        out = {"web": self._post(f"{WEB_BASE}/dapi/auth/logout",
                                 self._web_headers(), {})}
        if not out["web"].get("ok"):
            out["native"] = self._post(f"{PROFILE_BASE}/api/v1/app/logout",
                                       self._native_headers(), {})
        return out

    def refresh_login(self) -> dict:
        """Re-mint a session from the stored tid via the ozone sign-in route."""
        body = {
            "tid":        self.tid,
            "deviceId":   self.device_id,
            "swuid":      self.swuid,
            "androidId":  self.android_id,
            "cloningSignalsData": {
                "appFilesDirPathInvalid": 0, "developerModeEnabled": 0,
                "deviceModelVmos": 0, "emulatorStatus": 0,
                "packageName": "in.swiggy.android", "workProfileEnabled": 0,
            },
        }
        r = self._post(f"{PROFILE_BASE}/v1/accounts/signInWithTID",
                       self._native_headers(), body)
        d = r.get("data") or {}
        inner = d.get("data") if isinstance(d.get("data"), dict) else d
        r["token"] = (inner.get("token") or inner.get("accessToken")
                      or d.get("token") or "")
        r["sid"]   = inner.get("sid") or d.get("sid") or ""
        r["tid"]   = inner.get("tid") or d.get("tid") or ""
        r["customerId"] = str(inner.get("customerId") or inner.get("userId")
                              or inner.get("userid") or "")
        return r

    def logout_all_devices(self) -> dict:
        return self._post(f"{PROFILE_BASE}/api/v1/app/logout",
                          self._native_headers(), {"allDevices": True})


# ── result formatting helpers ────────────────────────────────────────────────
def extract_orders(res: dict) -> list[dict]:
    """Pull an order list out of an MCP get_orders result, shape-agnostic."""
    d = res.get("data") if isinstance(res, dict) else None
    if isinstance(d, list):
        return [x for x in d if isinstance(x, dict)]
    if isinstance(d, dict):
        for key in ("orders", "orderList", "order_list", "data", "results", "items"):
            v = d.get(key)
            if isinstance(v, list):
                return [x for x in v if isinstance(x, dict)]
            if isinstance(v, dict):
                for k2 in ("orders", "orderList", "results", "items"):
                    v2 = v.get(k2)
                    if isinstance(v2, list):
                        return [x for x in v2 if isinstance(x, dict)]
    return []


def _first(d: dict, *keys, default=None):
    for k in keys:
        if k in d and d[k] not in (None, ""):
            return d[k]
    return default


def food_cart_item(menu_item_id, name, cost, quantity: int = 1,
                   addons: list | None = None) -> dict:
    return {"menu_item_id": str(menu_item_id), "name": str(name),
            "cost": cost, "quantity": int(quantity), "addons": addons or []}


def iter_dicts(obj: Any):
    if isinstance(obj, dict):
        yield obj
        for v in obj.values():
            yield from iter_dicts(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from iter_dicts(v)


def extract_food_items(menu_res: dict, limit: int = 40) -> list[dict]:
    """Best-effort walk of a menu/search payload for addable dishes."""
    seen: set[str] = set()
    out: list[dict] = []
    for d in iter_dicts(menu_res.get("data")):
        iid = _first(d, "id", "menu_item_id", "menuItemId", "itemId", default=None)
        name = d.get("name")
        if not isinstance(iid, (str, int)) or not iid or not name:
            continue
        iid = str(iid)
        price = d.get("price")
        if price is None:
            price = d.get("defaultPrice")
        if price is None:
            price = d.get("final_price", d.get("finalPrice"))
        if price is None or iid in seen:
            continue
        seen.add(iid)
        out.append({
            "id": iid,
            "name": str(name)[:70],
            "price": price,
            "restaurant_id": str(d.get("restaurant_id") or d.get("restaurantId") or ""),
            "restaurant": str(d.get("restaurant_name") or d.get("restaurantName") or "")[:60],
            "veg": d.get("isVeg"),
            "in_stock": bool(d.get("inStock", True)),
        })
        if len(out) >= limit:
            break
    return out


def format_order_line(o: dict) -> str:
    oid   = _first(o, "orderId", "order_id", "id", "orderJobId", default="?")
    total = _first(o, "total", "orderTotal", "order_total", "grandTotal",
                   "grand_total", "amount", "netTotal", default=None)
    status = _first(o, "status", "orderStatus", "order_status", "state", default="?")
    when  = _first(o, "orderTime", "order_time", "createdAt", "created_at",
                   "date", "orderDate", default="")
    amount = _money(total) if total is not None else "?"
    tail = f" · {status}"
    if when:
        tail += f" · {when}"
    return f"#{oid} · {amount}{tail}"


def summarize(res: dict) -> str:
    if res.get("ok"):
        return "ok"
    return f"{res.get('status') or ''} {res.get('error') or ''}".strip() or "error"
