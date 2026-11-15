"""HTTP server and JSON API for the dashboard.

Stdlib only — ``ThreadingHTTPServer`` plus a small regex router — so the
dashboard runs on the same interpreter as the bot with nothing to install.
Blocking Swiggy calls happen in worker threads, one serialised stream per
account, which is exactly what the ``http.server`` thread-per-request model
already gives us.
"""
from __future__ import annotations

import json
import re
import secrets
import traceback
from html import escape as html_escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from . import config, login, scan, storage
from .client import Fleet
from .proxies import ProxyPool

POOL = ProxyPool()
FLEET = Fleet(POOL)
SCANNER = scan.Scanner(POOL)

ROUTES: list[tuple[str, re.Pattern, object]] = []


def route(method: str, pattern: str):
    compiled = re.compile("^" + re.sub(r"\{(\w+)\}", r"(?P<\1>[^/]+)", pattern) + "$")

    def register(fn):
        ROUTES.append((method.upper(), compiled, fn))
        return fn

    return register


def param(ctx: dict, name: str, default: str = "") -> str:
    value = ctx["params"].get(name)
    if value is None:
        value = ctx["query"].get(name, default)
    return str(value)


def int_param(ctx: dict, name: str, default: int) -> int:
    try:
        return int(param(ctx, name) or default)
    except (TypeError, ValueError):
        return default


def float_param(ctx: dict, name: str) -> float:
    raw = param(ctx, name)
    if raw in ("", None):
        raise ValueError(f"{name} is required")
    return float(raw)


def body_param(ctx: dict, name: str, default=""):
    value = ctx["body"].get(name, default)
    return value


# ═══ health / bootstrap ══════════════════════════════════════════════════════
@route("GET", "/api/health")
def health(ctx):
    return {"ok": True, "sessions": len(storage.list_sessions()),
            "proxies": len(POOL), "auth_required": bool(config.ACCESS_TOKEN)}


@route("GET", "/api/stats")
def stats(ctx):
    counts: dict[str, int] = {}
    for record in storage.list_sessions():
        status = str(record.get("sessionStatus") or "UNKNOWN").upper()
        counts[status] = counts.get(status, 0) + 1
    return {"ok": True, "counts": counts, "total": sum(counts.values())}


# ═══ sessions ════════════════════════════════════════════════════════════════
@route("GET", "/api/sessions")
def sessions_list(ctx):
    rows = []
    for record in storage.list_sessions():
        public = storage.public(record)
        public["proxy"] = POOL.pick(record.get("mobile", "")) or ""
        rows.append(public)
    return {"ok": True, "sessions": rows}


@route("POST", "/api/sessions/check")
def sessions_check(ctx):
    mobiles = body_param(ctx, "mobiles") or []
    if not isinstance(mobiles, list):
        mobiles = []
    results = FLEET.check_many([str(m) for m in mobiles])
    return {"ok": True, "results": results}


@route("GET", "/api/sessions/{mobile}")
def session_detail(ctx):
    mobile = param(ctx, "mobile")
    record = storage.get_session(mobile)
    if not record:
        raise KeyError("unknown session")
    public = storage.public(record)
    public["proxy"] = POOL.pick(mobile) or ""
    return {"ok": True, "session": public}


@route("DELETE", "/api/sessions/{mobile}")
def session_delete(ctx):
    mobile = param(ctx, "mobile")
    POOL.release(mobile)
    removed = storage.delete_session(mobile)
    storage.activity("session", mobile, "deleted from dashboard")
    return {"ok": removed, "removed": removed}


@route("POST", "/api/sessions/{mobile}/refresh")
def session_refresh(ctx):
    return {"ok": True, **FLEET.refresh(param(ctx, "mobile"))}


@route("POST", "/api/sessions/{mobile}/geo")
def session_geo(ctx):
    mobile = param(ctx, "mobile")
    try:
        lat = float(body_param(ctx, "latitude"))
        lng = float(body_param(ctx, "longitude"))
    except (TypeError, ValueError):
        raise ValueError("latitude and longitude are required numbers")
    return {"ok": True, **FLEET.set_geo(mobile, lat, lng)}


@route("GET", "/api/account/{mobile}")
def account_overview(ctx):
    return {"ok": True, **FLEET.overview(param(ctx, "mobile"))}


# ═══ login ═══════════════════════════════════════════════════════════════════
@route("POST", "/api/login/send")
def login_send(ctx):
    return login.send_otp(str(body_param(ctx, "mobile")), POOL)


@route("POST", "/api/login/verify")
def login_verify(ctx):
    return login.verify_otp(str(body_param(ctx, "ticket")), str(body_param(ctx, "otp")))


@route("POST", "/api/im/{mobile}/addresses/create")
def im_address_create(ctx):
    mobile = param(ctx, "mobile")
    fields = ctx["body"] if isinstance(ctx["body"], dict) else {}
    return {"ok": True, **FLEET.im_address_create(mobile, fields)}


@route("DELETE", "/api/im/{mobile}/addresses/{address_id}")
def im_address_delete(ctx):
    return {"ok": True, **FLEET.im_address_delete(param(ctx, "mobile"),
                                                  param(ctx, "address_id"))}


@route("GET", "/api/im/{mobile}/go-to")
def im_go_to(ctx):
    return {"ok": True, **FLEET.im_go_to_items(param(ctx, "mobile"),
                                               param(ctx, "address_id"))}


@route("GET", "/api/im/{mobile}/coupons")
def im_coupons(ctx):
    return {"ok": True, **FLEET.im_coupons(param(ctx, "mobile"),
                                           param(ctx, "address_id"))}


@route("POST", "/api/im/{mobile}/coupon")
def im_coupon_apply(ctx):
    address_id = str(body_param(ctx, "address_id"))
    code = str(body_param(ctx, "code") or body_param(ctx, "coupon_code")).strip()
    if not address_id or not code:
        raise ValueError("address_id and code are required")
    return {"ok": True, **FLEET.im_apply_coupon(param(ctx, "mobile"), address_id, code)}


@route("POST", "/api/im/{mobile}/coupon/remove")
def im_coupon_remove(ctx):
    address_id = str(body_param(ctx, "address_id"))
    if not address_id:
        raise ValueError("address_id is required")
    return {"ok": True, **FLEET.im_remove_coupon(
        param(ctx, "mobile"), address_id,
        str(body_param(ctx, "code") or body_param(ctx, "coupon_code")))}


@route("GET", "/api/im/{mobile}/fillers")
def im_fillers(ctx):
    ceiling = param(ctx, "max_price")
    return {"ok": True, **FLEET.im_fillers(
        param(ctx, "mobile"), param(ctx, "address_id"),
        float(ceiling) if ceiling else None)}


# ═══ group cart ══════════════════════════════════════════════════════════════
@route("GET", "/api/group/{mobile}")
def group_info(ctx):
    group_cart_id = param(ctx, "group_cart_id")
    if not group_cart_id:
        raise ValueError("group_cart_id is required")
    return {"ok": True, **FLEET.group_info(param(ctx, "mobile"), group_cart_id)}


@route("POST", "/api/group/{mobile}/create")
def group_create(ctx):
    restaurant_id = str(body_param(ctx, "restaurant_id"))
    if not restaurant_id:
        raise ValueError("restaurant_id is required")
    return {"ok": True, **FLEET.group_create(param(ctx, "mobile"), restaurant_id)}


@route("POST", "/api/group/{mobile}/join")
def group_join(ctx):
    group_cart_id = str(body_param(ctx, "group_cart_id"))
    if not group_cart_id:
        raise ValueError("group_cart_id is required")
    return {"ok": True, **FLEET.group_join(param(ctx, "mobile"), group_cart_id,
                                           str(body_param(ctx, "restaurant_id")))}


@route("POST", "/api/group/{mobile}/leave")
def group_leave(ctx):
    group_cart_id = str(body_param(ctx, "group_cart_id"))
    if not group_cart_id:
        raise ValueError("group_cart_id is required")
    return {"ok": True, **FLEET.group_leave(param(ctx, "mobile"), group_cart_id)}


@route("POST", "/api/group/{mobile}/update")
def group_update(ctx):
    group_cart_id = str(body_param(ctx, "group_cart_id"))
    if not group_cart_id:
        raise ValueError("group_cart_id is required")
    items = body_param(ctx, "items")
    if items is not None and not isinstance(items, list):
        raise ValueError("items must be a list")
    return {"ok": True, **FLEET.group_update(param(ctx, "mobile"), group_cart_id,
                                             items, str(body_param(ctx, "restaurant_id")))}


# ═══ templates ═══════════════════════════════════════════════════════════════
@route("GET", "/api/templates")
def templates_list(ctx):
    return {"ok": True, "templates": storage.templates()}


@route("POST", "/api/templates/save")
def templates_save(ctx):
    kind = str(body_param(ctx, "kind"))
    name = str(body_param(ctx, "name"))
    result = storage.save_template(kind, name, body_param(ctx, "payload"))
    storage.activity("template", "", f"saved {kind}/{name}")
    return result


@route("POST", "/api/templates/delete")
def templates_delete(ctx):
    kind = str(body_param(ctx, "kind"))
    name = str(body_param(ctx, "name"))
    result = storage.delete_template(kind, name)
    storage.activity("template", "", f"deleted {kind}/{name}")
    return result


# ═══ share links (single-use, 24 h) ══════════════════════════════════════════
# Swiggy exposes no share-token API for carts or addresses, so the token is
# dashboard-local: it carries the address/geo/item payload, the receiver opens
# /s/<token>, and the server hands the payload over exactly once.
SHARE_KINDS = ("cart", "address", "group", "order")


def _share_geo(payload: dict, mobile: str) -> dict:
    """Coordinates: body wins, then the session record, then nothing."""
    geo = payload.get("geo") if isinstance(payload.get("geo"), dict) else {}
    lat, lng = geo.get("lat") or geo.get("latitude"), geo.get("lng") or geo.get("longitude")
    if lat in (None, "") or lng in (None, ""):
        record = storage.get_session(mobile) if mobile else None
        lat = lat if lat not in (None, "") else (record or {}).get("latitude")
        lng = lng if lng not in (None, "") else (record or {}).get("longitude")
    out: dict[str, float] = {}
    for key, value in (("lat", lat), ("lng", lng)):
        try:
            if value not in (None, ""):
                out[key] = float(value)
        except (TypeError, ValueError):
            continue
    return out


def _share_items(payload: dict) -> list[dict]:
    items = payload.get("items")
    if not isinstance(items, list):
        return []
    rows = []
    for row in items[:40]:
        if not isinstance(row, dict):
            continue
        rows.append({
            "id": str(row.get("spinId") or row.get("spin_id") or row.get("id")
                      or row.get("itemId") or ""),
            "name": str(row.get("name") or row.get("itemName") or "")[:90],
            "quantity": int(row.get("quantity") or 1),
            "price": row.get("price") if isinstance(row.get("price"), (int, float)) else None,
            "restaurant_id": str(row.get("restaurant_id") or row.get("restaurantId") or ""),
        })
    return rows


def _share_link(token: str) -> dict:
    path = f"/s/{token}"
    base = config.SHARE_BASE_URL.rstrip("/")
    return {"path": path, "url": f"{base}{path}" if base else ""}


@route("POST", "/api/share/create")
def share_create(ctx):
    mobile = str(body_param(ctx, "mobile")).strip()
    kind = str(body_param(ctx, "kind") or "cart").strip().lower()
    if kind not in SHARE_KINDS:
        raise ValueError(f"kind must be one of {', '.join(SHARE_KINDS)}")
    raw = body_param(ctx, "payload")
    payload = raw if isinstance(raw, dict) else {}
    domain = str(body_param(ctx, "domain") or payload.get("domain") or "im").strip().lower()
    if domain not in ("im", "food"):
        raise ValueError("domain must be im or food")

    address = payload.get("address") if isinstance(payload.get("address"), dict) else {}
    address_id = str(body_param(ctx, "address_id") or address.get("id") or "").strip()
    if kind in ("address", "cart") and not address_id:
        raise ValueError("address_id is required — the receiver needs a delivery address")

    bundle = {
        "kind": kind,
        "domain": domain,
        "created_by": mobile,
        "address": {
            "id": address_id,
            "label": str(address.get("label") or address.get("addressCategory") or "")[:40],
            "line": str(address.get("line") or address.get("fullAddress")
                        or address.get("addressLine") or "")[:220],
            "category": str(address.get("category") or address.get("addressCategory") or "")[:20],
        } if address_id or address else {},
        "geo": _share_geo(payload, mobile),
        "restaurant_id": str(body_param(ctx, "restaurant_id")
                             or payload.get("restaurant_id") or "")[:40],
        "restaurant_name": str(body_param(ctx, "restaurant_name")
                               or payload.get("restaurant_name") or "")[:90],
        "items": _share_items(payload),
        "group": payload.get("group") if isinstance(payload.get("group"), dict) else None,
        "order_id": str(body_param(ctx, "order_id") or payload.get("order_id") or "")[:40],
        "note": str(body_param(ctx, "note") or payload.get("note") or "")[:200],
    }
    ttl = int(body_param(ctx, "ttl") or 0) or None
    record = storage.share_create(bundle, ttl=ttl, created_by=mobile)
    storage.activity("share", mobile, f"{kind} link {record['token']} → {record['expires']}")
    return {"ok": True, **record, **_share_link(record["token"])}


@route("GET", "/api/shares")
def shares_list(ctx):
    return {"ok": True, "shares": storage.shares_all(), "ttl": config.SHARE_TTL}


@route("GET", "/api/share/{token}")
def share_read(ctx):
    record = storage.share_get(param(ctx, "token"))
    return {**record, **_share_link(record.get("token", ""))}


@route("POST", "/api/share/{token}/consume")
def share_consume(ctx):
    mobile = str(body_param(ctx, "mobile")).strip()
    result = storage.share_consume(param(ctx, "token"), consumer=mobile)
    if not result.get("ok"):
        raise ValueError(str(result.get("error") or "this link cannot be claimed"))
    storage.activity("share", mobile or result.get("by", ""),
                     f"claimed {result['token']} ({result.get('payload', {}).get('kind', '')})")
    return result


# ═══ tags · incognito ════════════════════════════════════════════════════════
@route("GET", "/api/tags")
def tags_list(ctx):
    return {"ok": True, "tags": storage.tags_all(), "domains": list(storage.TAG_DOMAINS)}


@route("POST", "/api/sessions/{mobile}/mode")
def session_mode(ctx):
    return storage.set_mode(param(ctx, "mobile"), str(body_param(ctx, "mode", "normal")))


@route("POST", "/api/sessions/{mobile}/tags/refresh")
def session_tags_refresh(ctx):
    """Read order history and set the per-number counters from it.

    The count is the number of orders the account can prove, not a local tally —
    a re-run replaces the tag instead of doubling it.
    """
    mobile = param(ctx, "mobile")
    if not storage.get_session(mobile):
        raise KeyError("unknown session")
    address_id = str(body_param(ctx, "address_id") or "").strip()
    results = {
        "food": FLEET.food_orders(mobile, count=int_param(ctx, "count", 25),
                                  address_id=address_id),
        "im": FLEET.im_orders(mobile, count=int_param(ctx, "count", 25)),
    }
    counts: dict[str, int] = {}
    errors: dict[str, str] = {}
    for domain, result in results.items():
        if result.get("ok"):
            counts[domain] = len(result.get("orders") or [])
        else:
            errors[domain] = str(result.get("error") or "order history unavailable")
    if not counts:
        return {"ok": False, "error": "; ".join(errors.values()) or "no order history",
                "mobile": mobile, "tags": storage.tags_for(mobile)}
    for domain, count in counts.items():
        storage.tag_set(mobile, domain, count, source="order-history")
    storage.activity("session", mobile,
                     "tags ← " + ", ".join(f"{k}:{v}" for k, v in counts.items()))
    return {"ok": True, "mobile": mobile, "counts": counts, "errors": errors,
            "tags": storage.tags_for(mobile)}



# ═══ proxies ═════════════════════════════════════════════════════════════════
@route("GET", "/api/proxies")
def proxies_list(ctx):
    force = param(ctx, "test") == "1"
    return {"ok": True, "proxies": POOL.snapshot(force=force)}


@route("POST", "/api/proxies/test")
def proxies_test(ctx):
    return {"ok": True, "proxies": POOL.snapshot(force=True)}


@route("POST", "/api/proxies/reload")
def proxies_reload(ctx):
    POOL.reload()
    return {"ok": True, "proxies": POOL.snapshot()}


@route("POST", "/api/proxies/assign")
def proxies_assign(ctx):
    mobile = str(body_param(ctx, "mobile"))
    proxy = str(body_param(ctx, "proxy"))
    if not mobile or not proxy:
        raise ValueError("mobile and proxy are required")
    POOL.assign(mobile, proxy)
    return {"ok": True, "mobile": mobile, "proxy": POOL.pick(mobile)}


# ═══ instamart ═══════════════════════════════════════════════════════════════
@route("GET", "/api/im/{mobile}/addresses")
def im_addresses(ctx):
    return {"ok": True, **FLEET.im_addresses(param(ctx, "mobile"))}


@route("GET", "/api/im/{mobile}/search")
def im_search(ctx):
    query = param(ctx, "q")
    if not query:
        raise ValueError("q is required")
    return {"ok": True, **FLEET.im_search(param(ctx, "mobile"), query,
                                          param(ctx, "address_id"))}


@route("GET", "/api/im/{mobile}/cart")
def im_cart(ctx):
    return {"ok": True, **FLEET.im_cart(param(ctx, "mobile"))}


@route("GET", "/api/im/{mobile}/bill")
def im_bill(ctx):
    return {"ok": True, **FLEET.im_bill(param(ctx, "mobile"))}


@route("POST", "/api/im/{mobile}/cart")
def im_cart_update(ctx):
    items = body_param(ctx, "items") or []
    if not isinstance(items, list):
        raise ValueError("items must be a list")
    return {"ok": True, **FLEET.im_set_cart(param(ctx, "mobile"), items,
                                            str(body_param(ctx, "address_id")))}


@route("POST", "/api/im/{mobile}/cart/clear")
def im_cart_clear(ctx):
    return {"ok": True, **FLEET.im_clear_cart(param(ctx, "mobile"))}


@route("GET", "/api/im/{mobile}/payments")
def im_payments(ctx):
    return {"ok": True, **FLEET.im_payments(param(ctx, "mobile"))}


@route("POST", "/api/im/{mobile}/checkout")
def im_checkout(ctx):
    address_id = str(body_param(ctx, "address_id"))
    if not address_id:
        raise ValueError("address_id is required")
    return {"ok": True, **FLEET.im_checkout(
        param(ctx, "mobile"), address_id,
        payment_method=str(body_param(ctx, "payment_method", "Cash")),
        intent_app=str(body_param(ctx, "intent_app", "")),
        qr=bool(body_param(ctx, "qr", False)),
        confirm_duplicate=bool(body_param(ctx, "confirm_duplicate", False)))}


@route("POST", "/api/im/{mobile}/payment-status")
def im_payment_status(ctx):
    paas_id = str(body_param(ctx, "paas_id"))
    if not paas_id:
        raise ValueError("paas_id is required (from the checkout response)")
    return {"ok": True, **FLEET.im_payment_status(
        param(ctx, "mobile"), paas_id,
        order_id=str(body_param(ctx, "order_id", "")),
        address_id=str(body_param(ctx, "address_id", "")),
        cart_id=str(body_param(ctx, "cart_id", "")))}


@route("POST", "/api/im/{mobile}/confirm")
def im_confirm(ctx):
    order_id = str(body_param(ctx, "order_id"))
    if not order_id:
        raise ValueError("order_id is required")
    return {"ok": True, **FLEET.im_confirm(
        param(ctx, "mobile"), order_id,
        transaction_id=str(body_param(ctx, "transaction_id", "")),
        paas_id=str(body_param(ctx, "paas_id", "")),
        address_id=str(body_param(ctx, "address_id", "")),
        cart_id=str(body_param(ctx, "cart_id", "")))}


@route("GET", "/api/im/{mobile}/orders")
def im_orders(ctx):
    return {"ok": True, **FLEET.im_orders(
        param(ctx, "mobile"), count=int_param(ctx, "count", 15),
        active_only=param(ctx, "active") == "1")}


@route("GET", "/api/im/{mobile}/track")
def im_track(ctx):
    order_id = param(ctx, "order_id")
    if not order_id:
        raise ValueError("order_id is required")
    return {"ok": True, **FLEET.im_track(param(ctx, "mobile"), order_id,
                                         float_param(ctx, "lat"), float_param(ctx, "lng"))}


# ═══ food ════════════════════════════════════════════════════════════════════
@route("GET", "/api/food/{mobile}/addresses")
def food_addresses(ctx):
    return {"ok": True, **FLEET.food_addresses(param(ctx, "mobile"))}


@route("GET", "/api/food/{mobile}/menu")
def food_menu(ctx):
    restaurant_id = param(ctx, "restaurant_id")
    if not restaurant_id:
        raise ValueError("restaurant_id is required")
    address_id = param(ctx, "address_id")
    lat = param(ctx, "lat")
    lng = param(ctx, "lng")
    return {"ok": True, **FLEET.food_menu(
        param(ctx, "mobile"), restaurant_id, address_id,
        float(lat) if lat else None, float(lng) if lng else None,
        page=int_param(ctx, "page", 1))}


@route("GET", "/api/food/{mobile}/restaurants")
def food_restaurants(ctx):
    query = param(ctx, "q")
    if not query:
        raise ValueError("q is required")
    return {"ok": True, **FLEET.food_search_restaurants(
        param(ctx, "mobile"), query, param(ctx, "address_id"))}


@route("GET", "/api/food/{mobile}/search")
def food_search(ctx):
    query = param(ctx, "q")
    if not query:
        raise ValueError("q is required")
    return {"ok": True, **FLEET.food_search_menu(
        param(ctx, "mobile"), query, param(ctx, "address_id"))}


@route("GET", "/api/food/{mobile}/cart")
def food_cart(ctx):
    address_id = param(ctx, "address_id")
    if not address_id:
        raise ValueError("address_id is required")
    return {"ok": True, **FLEET.food_cart(param(ctx, "mobile"), address_id)}


@route("POST", "/api/food/{mobile}/cart")
def food_cart_update(ctx):
    address_id = str(body_param(ctx, "address_id"))
    restaurant_id = str(body_param(ctx, "restaurant_id"))
    if not address_id or not restaurant_id:
        raise ValueError("address_id and restaurant_id are required")
    items = body_param(ctx, "items") or []
    if not isinstance(items, list):
        raise ValueError("items must be a list")
    return {"ok": True, **FLEET.food_set_cart(
        param(ctx, "mobile"), address_id, restaurant_id, items,
        restaurant_name=str(body_param(ctx, "restaurant_name", "")),
        cutlery=bool(body_param(ctx, "cutlery", False)))}


@route("POST", "/api/food/{mobile}/cart/flush")
def food_cart_flush(ctx):
    return {"ok": True, **FLEET.food_flush(param(ctx, "mobile"))}


@route("GET", "/api/food/{mobile}/coupons")
def food_coupons(ctx):
    address_id = param(ctx, "address_id")
    restaurant_id = param(ctx, "restaurant_id")
    if not address_id or not restaurant_id:
        raise ValueError("address_id and restaurant_id are required")
    return {"ok": True, **FLEET.food_coupons(param(ctx, "mobile"), address_id,
                                             restaurant_id, param(ctx, "code"))}


@route("POST", "/api/food/{mobile}/coupon")
def food_coupon_apply(ctx):
    address_id = str(body_param(ctx, "address_id"))
    code = str(body_param(ctx, "coupon_code"))
    if not address_id or not code:
        raise ValueError("address_id and coupon_code are required")
    return {"ok": True, **FLEET.food_apply_coupon(
        param(ctx, "mobile"), address_id, code,
        cart_id=body_param(ctx, "cart_id"))}


@route("GET", "/api/food/{mobile}/payments")
def food_payments(ctx):
    address_id = param(ctx, "address_id")
    if not address_id:
        raise ValueError("address_id is required")
    amount = float_param(ctx, "cart_amount")
    return {"ok": True, **FLEET.food_payments(param(ctx, "mobile"), address_id,
                                              float(amount) if amount else None)}


@route("POST", "/api/food/{mobile}/place")
def food_place(ctx):
    address_id = str(body_param(ctx, "address_id"))
    if not address_id:
        raise ValueError("address_id is required")
    return {"ok": True, **FLEET.food_place(
        param(ctx, "mobile"), address_id,
        payment_method=str(body_param(ctx, "payment_method", "COD")),
        intent_app=str(body_param(ctx, "intent_app", "")),
        generate_qr=bool(body_param(ctx, "generate_qr", False)),
        note=str(body_param(ctx, "note", "")))}


@route("POST", "/api/food/{mobile}/payment-status")
def food_payment_status(ctx):
    paas_id = str(body_param(ctx, "paas_id"))
    if not paas_id:
        raise ValueError("paas_id is required")
    return {"ok": True, **FLEET.food_payment_status(
        param(ctx, "mobile"), paas_id,
        order_id=str(body_param(ctx, "order_id", "")),
        address_id=str(body_param(ctx, "address_id", "")),
        cart_id=str(body_param(ctx, "cart_id", "")))}


@route("POST", "/api/food/{mobile}/confirm")
def food_confirm(ctx):
    order_id = str(body_param(ctx, "order_id"))
    if not order_id:
        raise ValueError("order_id is required")
    return {"ok": True, **FLEET.food_confirm(
        param(ctx, "mobile"), order_id,
        transaction_id=str(body_param(ctx, "transaction_id", "")),
        paas_id=str(body_param(ctx, "paas_id", "")),
        address_id=str(body_param(ctx, "address_id", "")),
        cart_id=str(body_param(ctx, "cart_id", "")))}


@route("GET", "/api/food/{mobile}/orders")
def food_orders(ctx):
    return {"ok": True, **FLEET.food_orders(param(ctx, "mobile"),
                                            count=int_param(ctx, "count", 15),
                                            address_id=param(ctx, "address_id"))}


@route("GET", "/api/food/{mobile}/bill")
def food_bill(ctx):
    return {"ok": True, **FLEET.food_bill(param(ctx, "mobile"),
                                          param(ctx, "address_id"))}


@route("GET", "/api/food/{mobile}/track")
def food_track(ctx):
    order_id = param(ctx, "order_id")
    if not order_id:
        raise ValueError("order_id is required")
    return {"ok": True, **FLEET.food_track(param(ctx, "mobile"), order_id)}


# ═══ wallet / offers ═════════════════════════════════════════════════════════
@route("GET", "/api/wallet/{mobile}")
def wallet(ctx):
    return {"ok": True, **FLEET.wallet(param(ctx, "mobile"))}


@route("GET", "/api/wallet/{mobile}/statement")
def wallet_statement(ctx):
    return {"ok": True, **FLEET.wallet_statement(param(ctx, "mobile"),
                                                 count=int_param(ctx, "count", 20))}


@route("POST", "/api/wallet/{mobile}/giftcard")
def wallet_giftcard(ctx):
    code = str(body_param(ctx, "code"))
    secret = str(body_param(ctx, "secret"))
    if not code or not secret:
        raise ValueError("code and secret (PIN) are required")
    return {"ok": True, **FLEET.claim_gift_card(param(ctx, "mobile"), code, secret)}


@route("GET", "/api/offers/{mobile}/food")
def offers_food(ctx):
    address_id = param(ctx, "address_id")
    restaurant_id = param(ctx, "restaurant_id")
    if not address_id or not restaurant_id:
        raise ValueError("address_id and restaurant_id are required")
    return {"ok": True, **FLEET.food_offers(param(ctx, "mobile"), address_id, restaurant_id)}


@route("GET", "/api/offers/{mobile}/payment")
def offers_payment(ctx):
    return {"ok": True, **FLEET.payment_offers(
        param(ctx, "mobile"), float_param(ctx, "lat"), float_param(ctx, "lng"),
        restaurant_id=param(ctx, "restaurant_id"),
        cart_value=int_param(ctx, "cart_value", 0))}


@route("GET", "/api/offers/{mobile}/list")
def offers_list(ctx):
    return {"ok": True, **FLEET.offers_list(param(ctx, "mobile"))}


@route("POST", "/api/offers/{mobile}/scratch")
def offers_scratch(ctx):
    action = str(body_param(ctx, "action", "assign"))
    if action not in ("assign", "unlock"):
        raise ValueError("action must be assign or unlock")
    payload = body_param(ctx, "payload") or {}
    if not isinstance(payload, dict):
        raise ValueError("payload must be an object")
    return {"ok": True, **FLEET.scratch(param(ctx, "mobile"), action, payload)}


# ═══ scan ════════════════════════════════════════════════════════════════════
@route("GET", "/api/scan")
def scan_state(ctx):
    return {"ok": True, **SCANNER.state()}


@route("POST", "/api/scan/start")
def scan_start(ctx):
    panels = body_param(ctx, "panels")
    if panels is not None and not isinstance(panels, list):
        raise ValueError("panels must be a list of URLs")
    workers = int(body_param(ctx, "workers") or scan.WORKERS)
    max_age = int(body_param(ctx, "max_age_minutes") or scan.MAX_AGE_MINUTES)
    otp_timeout = int(body_param(ctx, "otp_timeout") or scan.OTP_TIMEOUT)
    result = SCANNER.start(workers=workers, max_age=max_age,
                           otp_timeout=otp_timeout, panels=panels)
    if not result.get("ok"):
        raise ValueError(str(result.get("error") or "scan did not start"))
    return result


@route("POST", "/api/scan/stop")
def scan_stop(ctx):
    return {"ok": True, **SCANNER.stop()}


@route("GET", "/api/scan/panels")
def scan_panels(ctx):
    panels, dupes = scan.load_panels()
    disabled = sorted(scan.load_disabled())
    active = [p for p in panels if (urlparse(p).hostname or "").lower() not in disabled]
    return {"ok": True, "active": active, "disabled": disabled,
            "duplicates": dupes, "total": len(panels)}


@route("POST", "/api/scan/panels/reload")
def scan_panels_reload(ctx):
    result = scan_panels(ctx)
    storage.activity("scan", "", f"panels reloaded: {len(result['active'])} active")
    return result


@route("POST", "/api/scan/panels/probe")
def scan_panels_probe(ctx):
    raw = str(body_param(ctx, "panel"))
    if not raw:
        raise ValueError("panel is required")
    return {"ok": True, **scan.probe_panel(raw)}


# ═══ activity ════════════════════════════════════════════════════════════════
@route("GET", "/api/logs")
def logs(ctx):
    return {"ok": True, "entries": storage.recent_activity(int_param(ctx, "limit", 60))}


# ═══ http plumbing ═══════════════════════════════════════════════════════════
CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".svg": "image/svg+xml",
    ".ico": "image/x-icon",
}

# The receiver's page. Self-contained — no build step, no static dependency, so
# it renders on a phone that opened the link cold.
SHARE_PAGE_TEMPLATE = """<!doctype html>
<html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Swiggy share · {{TOKEN}}</title>
<style>
  :root{color-scheme:dark}
  *{box-sizing:border-box}
  body{margin:0;min-height:100vh;background:#0b0d10;color:#e6e8ea;
       font:15px/1.5 ui-sans-serif,system-ui,-apple-system,"Segoe UI",sans-serif;
       display:flex;align-items:flex-start;justify-content:center;padding:28px 16px}
  .wrap{width:100%;max-width:520px}
  .top{display:flex;align-items:center;gap:10px;margin-bottom:18px}
  .logo{width:34px;height:34px;border-radius:10px;background:#fc8019;color:#111;
        display:grid;place-items:center;font-weight:800}
  h1{font-size:18px;margin:0;font-weight:700}
  .badge{display:inline-block;margin-left:auto;font-size:11px;letter-spacing:.06em;
         text-transform:uppercase;padding:4px 9px;border-radius:999px;
         background:#1b2027;border:1px solid #2a313a;color:#9aa4b0}
  .card{background:#12161b;border:1px solid #222932;border-radius:14px;
        padding:16px;margin-bottom:12px}
  .row{display:flex;justify-content:space-between;gap:12px;padding:6px 0;
       border-bottom:1px dashed #222932;font-size:14px}
  .row:last-child{border:0}
  .row span:first-child{color:#8d97a2}
  .mono{font-family:ui-monospace,SFMono-Regular,Menlo,monospace}
  ul{list-style:none;margin:0;padding:0}
  li{display:flex;justify-content:space-between;gap:10px;padding:7px 0;
     border-bottom:1px dashed #222932;font-size:14px}
  li:last-child{border:0}
  button{width:100%;padding:13px 16px;border-radius:12px;border:0;cursor:pointer;
         background:#fc8019;color:#101215;font-size:15px;font-weight:700}
  button:disabled{background:#242b33;color:#67707b;cursor:not-allowed}
  .muted{color:#8d97a2;font-size:12.5px}
  .err{color:#ff8a8a}
  a{color:#fc8019}
  pre{white-space:pre-wrap;word-break:break-word;font-size:12px;color:#9aa4b0;
      background:#0e1216;border:1px solid #1d242c;border-radius:10px;padding:10px;
      max-height:220px;overflow:auto}
</style></head><body><div class="wrap">
  <div class="top"><div class="logo">S</div><h1>Shared Swiggy bundle</h1>
    <span class="badge">{{BADGE}}</span></div>
  <div class="card" id="summary"><div class="muted">reading link…</div></div>
  <button id="claim">Claim this link</button>
  <p class="muted" style="margin-top:10px">One use only. Expires {{EXPIRES}}.
     Claiming copies the address and items into this dashboard.</p>
  <div class="card" id="result" hidden></div>
  <pre id="raw" hidden></pre>
</div>
<script>
const TOKEN = "{{TOKEN}}";
const STATE = "{{STATE}}";
const $ = (sel) => document.querySelector(sel);
const esc = (v) => String(v == null ? "" : v).replace(/[&<>"']/g,
  (c) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const money = (v) => (v == null ? '' : '₹' + Number(v).toFixed(2));

async function start() {
  let rec = null;
  try {
    const res = await fetch('/api/share/' + encodeURIComponent(TOKEN));
    rec = await res.json();
  } catch (err) {
    $('#summary').innerHTML = '<div class="err">could not read the link: '
      + esc(err.message) + '</div>';
    return;
  }
  if (!rec || !rec.ok) {
    $('#summary').innerHTML = '<div class="err">'
      + esc((rec && (rec.error || rec.state)) || 'this link is not live') + '</div>';
    $('#claim').disabled = true;
    if (rec && rec.payload) $('#raw').hidden = false, $('#raw').textContent =
      JSON.stringify(rec.payload, null, 2);
    return;
  }
  const p = rec.payload || {};
  const addr = p.address || {};
  const rows = [];
  rows.push(['type', esc(p.kind || '')]);
  if (p.restaurant_name) rows.push(['restaurant', esc(p.restaurant_name)]);
  if (addr.line) rows.push(['address', esc(addr.line)]);
  if (addr.id) rows.push(['address id', '<span class="mono">' + esc(addr.id) + '</span>']);
  if (p.geo && p.geo.lat != null) rows.push(['location',
    '<span class="mono">' + esc(p.geo.lat) + ', ' + esc(p.geo.lng) + '</span>']);
  if (p.group && (p.group.cart_id || p.group.deeplink))
    rows.push(['group cart', '<span class="mono">'
      + esc(p.group.cart_id || p.group.deeplink) + '</span>']);
  if (p.order_id) rows.push(['order', '<span class="mono">' + esc(p.order_id) + '</span>']);
  if (p.created_by) rows.push(['shared by', esc(p.created_by)]);
  if (p.note) rows.push(['note', esc(p.note)]);
  const items = Array.isArray(p.items) ? p.items : [];
  const total = items.reduce((sum, it) => sum + (Number(it.price || 0) * (it.quantity || 1)), 0);
  $('#summary').innerHTML = rows.map(([k, v]) =>
      '<div class="row"><span>' + k + '</span><span>' + v + '</span></div>').join('')
    + (items.length ? '<div style="margin-top:10px"><ul>'
        + items.map((it) => '<li><span>' + esc(it.name) + ' × ' + esc(it.quantity)
            + '</span><span class="mono">' + money(it.price) + '</span></li>').join('')
        + '</ul><div class="row" style="margin-top:8px"><span>items</span><span>'
        + esc(items.length) + ' · ' + money(total) + '</span></div></div>' : '');
  if (STATE !== 'live') {
    $('#claim').disabled = true;
    $('#claim').textContent = 'Link ' + STATE;
  }
}

$('#claim').addEventListener('click', async () => {
  $('#claim').disabled = true;
  $('#claim').textContent = 'claiming…';
  let out = null;
  try {
    const res = await fetch('/api/share/' + encodeURIComponent(TOKEN) + '/consume',
      {method: 'POST', headers: {'Content-Type': 'application/json'},
       body: JSON.stringify({mobile: localStorage.getItem('dash.mobile') || ''})});
    out = await res.json();
  } catch (err) {
    out = {ok: false, error: err.message};
  }
  const box = $('#result');
  box.hidden = false;
  if (!out || !out.ok) {
    box.innerHTML = '<div class="err">' + esc((out && out.error) || 'claim failed')
      + '</div>';
    $('#claim').textContent = 'Link ' + ((out && out.state) || 'unusable');
    return;
  }
  box.innerHTML = '<div class="row"><span>claimed</span><span class="mono">'
    + esc(out.used_at || '') + '</span></div><div class="muted" style="margin-top:8px">'
    + 'payload copied — open the dashboard, pick a session, then '
    + '\"Import\" on the matching domain.</div>';
  $('#claim').textContent = 'Claimed';
  $('#raw').hidden = false;
  $('#raw').textContent = JSON.stringify(out.payload || {}, null, 2);
});

start();
</script></body></html>
"""

SHARE_PAGE_MISSING = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Swiggy share · unknown</title>
<style>body{background:#0b0d10;color:#e6e8ea;font:15px/1.5 system-ui,sans-serif;
 display:grid;place-items:center;min-height:100vh;margin:0;padding:24px}
 .card{max-width:420px;background:#12161b;border:1px solid #222932;border-radius:14px;
 padding:20px}.mono{font-family:ui-monospace,Menlo,monospace;color:#8d97a2;
 word-break:break-all;font-size:12px}</style></head>
<body><div class="card"><h1 style="font-size:17px;margin:0 0 8px">Link not found</h1>
<p style="color:#8d97a2;margin:0 0 10px">This token is not on the dashboard —
 it may have been swept after a week, or the link was mistyped.</p>
<p class="mono">{{TOKEN}}</p></div></body></html>
"""


class Handler(BaseHTTPRequestHandler):
    server_version = "SwiggyDashboard/1.0"
    protocol_version = "HTTP/1.1"

    # ── responses ────────────────────────────────────────────────────────────
    def _send(self, status: int, payload: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(payload)

    def _json(self, payload: dict, status: int = 200) -> None:
        self._send(status, json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                   "application/json; charset=utf-8")

    # ── auth ─────────────────────────────────────────────────────────────────
    def _authorised(self, query: dict) -> bool:
        if not config.ACCESS_TOKEN:
            return True
        supplied = (self.headers.get("X-Dashboard-Token")
                    or (query.get("token", [""])[0] if query else ""))
        return bool(supplied) and secrets.compare_digest(supplied, config.ACCESS_TOKEN)

    # ── dispatch ─────────────────────────────────────────────────────────────
    def do_GET(self):
        self._handle("GET")

    def do_POST(self):
        self._handle("POST")

    def do_DELETE(self):
        self._handle("DELETE")

    def do_HEAD(self):
        self._handle("GET")

    # ── share lander ─────────────────────────────────────────────────────────
    def _share_page(self, token: str) -> None:
        """The page a receiver opens. Reads the token server-side so an expired
        link renders as expired instead of a blank shell."""
        try:
            record = storage.share_get(token)
        except KeyError:
            self._send(404, SHARE_PAGE_MISSING.replace("{{TOKEN}}", html_escape(token))
                       .encode("utf-8"), "text/html; charset=utf-8")
            return
        state = record.get("state")
        self._send(200, SHARE_PAGE_TEMPLATE
                   .replace("{{TOKEN}}", html_escape(token))
                   .replace("{{STATE}}", html_escape(str(state)))
                   .replace("{{BADGE}}", html_escape({
                       "live": "live · single use",
                       "used": "already claimed",
                       "expired": "expired",
                   }.get(str(state), str(state))))
                   .replace("{{EXPIRES}}", html_escape(str(record.get("expires") or "—")))
                   .encode("utf-8"), "text/html; charset=utf-8")

    def _handle(self, method: str) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)
        if path.startswith("/s/") and method == "GET":
            self._share_page(path[len("/s/"):].strip("/"))
            return
        if not path.startswith("/api/"):
            self._static(path)
            return
        if not self._authorised(query):
            self._json({"ok": False, "error": "unauthorised"}, 401)
            return

        body: dict = {}
        if method in ("POST", "DELETE"):
            try:
                length = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                length = 0
            if length > config.MAX_BODY:
                self._json({"ok": False, "error": "body too large"}, 413)
                return
            raw = self.rfile.read(length) if length else b""
            if raw:
                try:
                    parsed_body = json.loads(raw.decode("utf-8"))
                    body = parsed_body if isinstance(parsed_body, dict) else {"value": parsed_body}
                except (ValueError, UnicodeDecodeError):
                    self._json({"ok": False, "error": "body must be JSON"}, 400)
                    return

        for route_method, pattern, handler in ROUTES:
            if route_method != method:
                continue
            match = pattern.match(path)
            if not match:
                continue
            ctx = {"params": match.groupdict(), "query": {k: v[0] for k, v in query.items()},
                   "body": body}
            try:
                result = handler(ctx)
                self._json(result if isinstance(result, dict) else {"ok": True, "result": result})
            except KeyError as exc:
                self._json({"ok": False, "error": str(exc).strip("'\"") or "not found"}, 404)
            except ValueError as exc:
                self._json({"ok": False, "error": str(exc)}, 400)
            except Exception as exc:  # noqa: BLE001 - surfaced to the UI, not swallowed
                traceback.print_exc()
                self._json({"ok": False, "error": f"{type(exc).__name__}: {exc}"[:300]}, 500)
            return
        self._json({"ok": False, "error": "no such route"}, 404)

    def _static(self, path: str) -> None:
        name = "index.html" if path in ("/", "") else path.lstrip("/")
        if name.startswith("static/"):
            name = name[len("static/"):]
        target = (config.STATIC_DIR / name).resolve()
        try:
            target.relative_to(config.STATIC_DIR.resolve())
        except ValueError:
            self._json({"ok": False, "error": "bad path"}, 403)
            return
        if not target.is_file():
            self._json({"ok": False, "error": "not found"}, 404)
            return
        content_type = CONTENT_TYPES.get(target.suffix, "application/octet-stream")
        self._send(200, target.read_bytes(), content_type)

    def log_message(self, fmt: str, *args) -> None:
        return


def main() -> None:
    server = ThreadingHTTPServer((config.BIND_HOST, config.BIND_PORT), Handler)
    server.daemon_threads = True
    print(f"bench dashboard → http://{config.BIND_HOST}:{config.BIND_PORT}")
    print(f"  sessions: {len(storage.list_sessions())}   proxies: {len(POOL)}"
          f"   auth: {'on' if config.ACCESS_TOKEN else 'off (localhost only)'}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nshutting down")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
