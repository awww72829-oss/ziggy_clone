"""Operations layer.

Wraps :mod:`account_ops` with the things the dashboard needs and the library
does not do: one sticky proxy per account, one serialised request stream per
account, human pacing on mutating calls, and cached liveness that writes its
result back into the shared session store.
"""
from __future__ import annotations

import random
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import account_ops

from . import config, storage
from .proxies import ProxyPool

EXPIRED_CODES = (401, 403)


# ── payload normalisers ──────────────────────────────────────────────────────
def _iter_dicts(obj: Any):
    if isinstance(obj, dict):
        yield obj
        for value in obj.values():
            yield from _iter_dicts(value)
    elif isinstance(obj, list):
        for value in obj:
            yield from _iter_dicts(value)


def _price(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.replace(",", "").strip())
        except ValueError:
            return None
    if isinstance(value, dict):
        for key in ("offerPrice", "discountedPrice", "finalPrice", "price",
                    "mrp", "value", "amount"):
            if key in value:
                found = _price(value[key])
                if found is not None:
                    return found
    return None


def variants(payload: Any, limit: int = 80) -> list[dict]:
    """Flatten an Instamart search payload into addable variants."""
    out: list[dict] = []
    seen: set[tuple] = set()
    for node in _iter_dicts(payload):
        spin = node.get("spinId") or node.get("spin_id")
        if not spin:
            continue
        name = (node.get("name") or node.get("displayName") or node.get("brandName")
                or node.get("productName") or node.get("title"))
        if not name:
            continue
        price = None
        for key in ("price", "discountedPrice", "offerPrice", "finalPrice",
                    "unitPrice", "mrp", "sellingPrice"):
            price = _price(node.get(key))
            if price is not None:
                break
        pack = (node.get("quantityDescription") or node.get("packSize")
                or node.get("unit") or node.get("weight") or "")
        sku = node.get("skuId") or node.get("sku_id") or ""
        key = (str(spin), str(sku), str(name), price)
        if key in seen:
            continue
        seen.add(key)
        out.append({
            "spinId": str(spin),
            "skuId": str(sku),
            "name": str(name)[:80],
            "pack": str(pack)[:40],
            "price": price,
            "in_stock": bool(node.get("inStock", node.get("available", True))),
        })
        if len(out) >= limit:
            break
    return out


def addresses(payload: Any) -> list[dict]:
    out: list[dict] = []
    seen: set[str] = set()
    for node in _iter_dicts(payload):
        raw_id = node.get("id") or node.get("addressId") or node.get("address_id")
        if not raw_id or not isinstance(raw_id, (str, int)):
            continue
        line = (node.get("addressLine") or node.get("address") or node.get("fullAddress")
                or node.get("displayAddress") or node.get("locality"))
        if not line:
            continue
        aid = str(raw_id)
        if aid in seen:
            continue
        seen.add(aid)
        # The saved-address list hands back "<handle>__<signature>". Every
        # other surface (get_cart's selectedAddress, delete_address) keys on
        # the bare handle, so keep both: id for calls, raw_id for display.
        bare = aid.split("__")[0] if "__" in aid else aid
        out.append({
            "id": bare,
            "raw_id": aid,
            "label": str(node.get("label") or node.get("addressTag")
                         or node.get("addressCategory") or "address")[:40],
            "line": str(line)[:160],
            "tag": str(node.get("addressTag") or "")[:40],
            "lat": node.get("latitude") or node.get("lat"),
            "lng": node.get("longitude") or node.get("lng"),
        })
    return out


def money(value: Any) -> str | None:
    amount = _price(value)
    if amount is None:
        return None
    return f"₹{amount:,.2f}"


def cart_summary(payload: Any) -> dict:
    """Normalise a food/IM cart payload into items + pricing + coupon.

    Food returns {"statusCode":0,"data":{cart_id,items,pricing,offers}}; IM
    returns {"items":[...],"billDetails":{...}}. Both collapse to one shape.
    """
    data = payload if isinstance(payload, dict) else {}
    inner = data.get("data") if isinstance(data.get("data"), dict) else data
    items = []
    raw_items = inner.get("items")
    if isinstance(raw_items, list):
        for row in raw_items:
            if not isinstance(row, dict):
                continue
            qty = int(row.get("quantity") or 1)
            unit = (_price(row.get("final_price")) or _price(row.get("price"))
                    or _price(row.get("subtotal")))
            items.append({
                "id": str(row.get("menu_item_id") or row.get("id") or ""),
                "name": str(row.get("name") or "item")[:80],
                "quantity": qty,
                "price": unit,
                "subtotal": (_price(row.get("subtotal"))
                             or (unit * qty if unit is not None else None)),
                "veg": row.get("is_veg"),
                "in_stock": bool(row.get("in_stock", True)),
            })
    pricing = inner.get("pricing") if isinstance(inner.get("pricing"), dict) else {}
    bill = inner.get("billDetails") if isinstance(inner.get("billDetails"), dict) else {}
    offers = inner.get("offers") if isinstance(inner.get("offers"), dict) else {}

    def pick(*keys, source=None):
        source = pricing if source is None else source
        for key in keys:
            if source.get(key) is not None:
                return source.get(key)
        return None

    return {
        "items": items,
        "item_count": (sum(i["quantity"] for i in items) if items
                       else int(inner.get("item_count") or 0)),
        "cart_id": inner.get("cart_id") or inner.get("cartId") or inner.get("id"),
        "restaurant": str((inner.get("restaurant") or {}).get("name")
                          or inner.get("restaurantName") or "")[:80],
        "pricing": {
            "item_total": pick("item_total", "itemTotal", "subtotal",
                               source=pricing or bill),
            "delivery": pick("delivery_charge", "deliveryCharge",
                             source=pricing or bill),
            "taxes": pick("taxes_and_charges", "taxesAndCharges",
                          source=pricing or bill),
            "to_pay": pick("to_pay", "toPay", "total", source=pricing or bill),
        },
        "coupon": {
            "code": offers.get("coupon_applied") or odds_code(offers),
            "discount": _price(offers.get("coupon_discount")),
        },
    }


def odds_code(offers: dict) -> str:
    """Best-effort coupon code out of an offers block."""
    for node in _iter_dicts(offers):
        if isinstance(node, dict):
            for key in ("couponCode", "coupon_code", "code"):
                val = node.get(key)
                if isinstance(val, str) and val:
                    return val
    return ""


# ── errors ───────────────────────────────────────────────────────────────────
# Swiggy answers most failures with HTTP 200 and a typed body, so an operator
# staring at "HTTP 200" learns nothing. Every Fleet method folds the response
# through ``explain`` before it reaches the UI.
ERROR_HINTS: tuple[tuple[str, str], ...] = (
    ("incorrect alg in mcp jwt",
     "Swiggy rejected the session token — re-mint it from Sessions, or log the number in again"),
    ("invalid_token", "session token rejected — re-mint it from Sessions"),
    ("invalid token", "session token rejected — re-mint it from Sessions"),
    ("token expired", "session token expired — re-mint it from Sessions"),
    ("session expired", "session expired — log the number in again"),
    ("no longer exists", "group cart no longer exists — the host left or it expired"),
    ("group_cart_restaurant_id_not_provided", "restaurant id missing from the join — Swiggy needs it"),
    ("group_cart_user_id_not_provided",
     "no user id on this session — the tid JWT carried no user_id, refresh the session"),
    ("no serviceability", "this address is outside the store's delivery radius"),
    ("out of stock", "one of the items went out of stock — re-read the cart and retry"),
    ("minimum order", "cart value is below the minimum for this address"),
    ("minimum_order", "cart value is below the minimum for this address"),
    ("invalid coupon", "Swiggy rejected the coupon code"),
    ("coupon not applicable", "that coupon does not apply to this cart"),
    ("coupon_expired", "that coupon expired"),
    ("address not found", "the address id is not on this account any more — reload addresses"),
    ("invalid address", "Swiggy rejected the address id — reload addresses and pick again"),
    ("cart is empty", "the cart is empty — add at least one item"),
    ("restaurant closed", "the restaurant is closed right now"),
)


def explain(result: dict, context: str = "request") -> str | None:
    """One actionable sentence for a failed call, or None when it worked."""
    if not isinstance(result, dict) or result.get("ok"):
        return None
    status = result.get("status")
    text = str(result.get("error") or "").strip()
    body = result.get("data")
    messages: list[str] = []
    for node in _iter_dicts(body):
        for key in ("statusMessage", "errorMessage", "errorDescription", "message"):
            value = node.get(key)
            if isinstance(value, str) and value.strip():
                messages.append(value.strip())
        codes = node.get("errorCodes")
        if isinstance(codes, list):
            messages.extend(str(code) for code in codes if code)
    haystack = " ".join([text, *messages[:8]]).lower()
    for needle, message in ERROR_HINTS:
        if needle in haystack:
            return message
    if status in EXPIRED_CODES:
        return "Swiggy rejected the session (HTTP %s) — re-mint the token" % status
    if status == 429:
        return "rate limited by Swiggy — wait a minute and retry"
    if isinstance(status, int) and status >= 500:
        return f"Swiggy returned HTTP {status} — retry in a moment"
    detail = text or (messages[0] if messages else "")
    if detail:
        return f"{context} failed: {detail[:180]}"
    if status:
        return f"{context} failed: HTTP {status}"
    return f"{context} failed"


# ── more payload normalisers ─────────────────────────────────────────────────
def _first(node: dict, *keys, default=None):
    for key in keys:
        if key in node and node[key] not in (None, ""):
            return node[key]
    return default


def _deep_number(obj: Any, keys: tuple[str, ...]) -> tuple[float | None, str]:
    """First numeric hit for any of ``keys`` anywhere in the payload."""
    for node in _iter_dicts(obj):
        for key in keys:
            if key in node and node[key] is not None:
                value = _price(node[key])
                if value is not None:
                    return value, key
    return None, ""


def group_items(payload: Any) -> list[dict]:
    """Every line sitting in a shared cart, tagged with the member who added it."""
    data = payload
    if isinstance(payload, dict) and isinstance(payload.get("data"), dict):
        data = payload["data"]
    if not isinstance(data, dict):
        return []
    carts = data.get("user_cart_map")
    if not isinstance(carts, dict):
        carts = data.get("userCartMap") if isinstance(data.get("userCartMap"), dict) else {}
    restaurant = data.get("restaurant_details")
    restaurant_id = ""
    if isinstance(restaurant, dict):
        restaurant_id = str(restaurant.get("restaurant_id") or restaurant.get("restaurantId") or "")
    rows: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for member, cart in carts.items():
        for node in _iter_dicts(cart):
            item_id = _first(node, "itemId", "item_id", "menu_item_id", "id")
            name = node.get("name") or node.get("itemName")
            quantity = node.get("quantity") or node.get("count") or node.get("qty")
            if not item_id or not isinstance(name, str) or not name.strip() or quantity is None:
                continue
            key = (str(item_id), str(member))
            if key in seen:
                continue
            seen.add(key)
            rows.append({
                "id": str(item_id),
                "name": name.strip()[:70],
                "quantity": int(quantity) if str(quantity).isdigit() else 1,
                "price": _price(node.get("price") or node.get("finalPrice")
                                or node.get("unitPrice") or node.get("subtotal")),
                "member": str(member)[:24],
                "restaurant_id": str(node.get("restaurantId") or restaurant_id),
            })
    return rows


def coupon_rows(payload: Any, limit: int = 30) -> list[dict]:
    """Coupons advertised in a cart/offer payload."""
    rows: list[dict] = []
    seen: set[str] = set()
    for node in _iter_dicts(payload):
        code = node.get("couponCode") or node.get("coupon_code") or node.get("code")
        if not isinstance(code, str) or not code.strip():
            continue
        code = code.strip()
        if code in seen:
            continue
        seen.add(code)
        rows.append({
            "code": code,
            "title": str(node.get("couponDescription") or node.get("description")
                         or node.get("title") or node.get("couponTitle") or "")[:140],
            "savings": money(node.get("discountAmount") or node.get("maxDiscount")
                             or node.get("discount") or node.get("savings")),
            "min_cart": _price(node.get("minCartValue") or node.get("min_cart_value")),
        })
        if len(rows) >= limit:
            break
    return rows


METHOD_WORDS = (
    ("bhim", "UPI · BHIM"),
    ("gpay", "UPI · Google Pay"),
    ("google pay", "UPI · Google Pay"),
    ("phonepe", "UPI · PhonePe"),
    ("paytm", "UPI · Paytm"),
    ("upi", "UPI"),
    ("credit", "Card · Credit"),
    ("debit", "Card · Debit"),
    ("card", "Card"),
    ("cod", "Cash on delivery"),
    ("cash", "Cash on delivery"),
    ("swiggymoney", "Swiggy Money"),
    ("swiggy money", "Swiggy Money"),
    ("wallet", "Wallet"),
    ("netbanking", "Netbanking"),
    ("lazypay", "LazyPay"),
)


def _method_label(text: str) -> str:
    lowered = text.lower()
    for needle, label in METHOD_WORDS:
        if needle in lowered:
            return label
    return ""


def payment_rows(payload: Any, limit: int = 30) -> list[dict]:
    """Per-method cash offers out of ``dapi/offers/payment``.

    The endpoint returns a nested blob whose leaf shape is not stable, so every
    node that carries a title wins; a method is attached when one can be read
    off the node or its own text ("BHIM ₹50 off" -> UPI · BHIM, ₹50).
    """
    rows: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for node in _iter_dicts(payload):
        title = (node.get("offerTitle") or node.get("title") or node.get("displayName")
                 or node.get("description") or node.get("offerDescription"))
        if not isinstance(title, str) or not title.strip():
            continue
        title = title.strip()
        raw_method = str(_first(node, "paymentMethod", "paymentMode", "method",
                                "paymentInstrument", "instrument", "mode", default=""))
        method = _method_label(raw_method) or _method_label(title) or raw_method[:24]
        amount = _price(_first(node, "discountAmount", "discount", "maxDiscount",
                               "offerAmount", "cashback", "savings", default=None))
        code = str(_first(node, "offerCode", "code", "couponCode", default=""))
        key = (method, title[:80])
        if key in seen:
            continue
        seen.add(key)
        rows.append({"method": method or "any", "title": title[:140],
                     "savings": money(amount), "amount": amount, "code": code[:40]})
        if len(rows) >= limit:
            break
    return rows


def _group_offers(rows: list[dict]) -> dict[str, list[dict]]:
    """Payment offers keyed by method label, insertion-ordered.

    The UI renders one row per payment method, so this is the shape it reads:
    ``{"UPI · BHIM": [{...}], "Card · Credit": [{...}]}``.
    """
    grouped: dict[str, list[dict]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        grouped.setdefault(str(row.get("method") or "any"), []).append(row)
    return grouped


def bill_breakdown(payload: Any) -> dict:
    """What the cart says is payable, line by line.

    Coupon discount, free cash, extra cash and wallet credit are pulled from the
    payload when present. Fields the payload does not carry come back None — the
    UI prints them as "—" rather than inventing a number.
    """
    data = payload if isinstance(payload, dict) else {}
    inner = data.get("data") if isinstance(data.get("data"), dict) else data
    if not isinstance(inner, dict):
        inner = {}
    bill = inner.get("billDetails") if isinstance(inner.get("billDetails"), dict) else {}
    pricing = inner.get("pricing") if isinstance(inner.get("pricing"), dict) else {}
    offers = inner.get("offers") if isinstance(inner.get("offers"), dict) else {}

    def pick(keys: tuple[str, ...]) -> float | None:
        for holder in (bill, pricing, inner):
            for key in keys:
                if holder.get(key) is not None:
                    value = _price(holder.get(key))
                    if value is not None:
                        return value
        return None

    lines: list[dict] = []

    def add(label: str, amount: float | None, kind: str = "") -> None:
        if amount is None:
            return
        lines.append({"label": label, "amount": amount, "kind": kind})

    item_total = pick(("itemTotal", "item_total", "subtotal", "itemsTotal"))
    delivery = pick(("deliveryCharge", "delivery_charge", "deliveryFee"))
    taxes = pick(("taxesAndCharges", "taxes_and_charges", "totalTaxes", "tax"))
    packing = pick(("packingCharge", "packing_charge"))
    platform = pick(("platformFee", "platform_fee", "surgeFee"))
    discount = pick(("couponDiscount", "coupon_discount", "totalDiscount", "discountApplied"))
    if discount is None:
        discount = _price(offers.get("coupon_discount")) if isinstance(offers, dict) else None
    free_cash, free_field = _deep_number(inner, ("freeCash", "free_cash", "freecash",
                                                 "freeCashApplied", "free_cash_applied"))
    extra_cash, extra_field = _deep_number(inner, ("extraCash", "extra_cash", "extracash",
                                                   "extraCashApplied", "extra_cash_applied"))
    wallet, wallet_field = _deep_number(inner, ("swiggyMoney", "swiggy_money",
                                                "swiggyMoneyApplied", "walletAmount"))
    cashback, _ = _deep_number(inner, ("cashback", "cashbackAmount"))
    to_pay = pick(("toPay", "to_pay", "grandTotal", "payableAmount", "netTotal", "total"))
    savings = pick(("totalSavings", "savings", "youSaved"))

    add("item total", item_total)
    add("delivery", delivery)
    add("taxes & charges", taxes)
    add("packing", packing)
    add("platform fee", platform)
    add("coupon discount", -discount if discount else None, "credit")
    add("free cash", -free_cash if free_cash else None, "credit")
    add("extra cash", -extra_cash if extra_cash else None, "credit")
    add("swiggy money", -wallet if wallet else None, "credit")
    add("cashback", -cashback if cashback else None, "credit")
    add("to pay", to_pay, "total")

    return {
        "item_total": item_total, "delivery": delivery, "taxes": taxes,
        "packing": packing, "platform_fee": platform,
        "coupon": {
            "code": (offers.get("coupon_applied") if isinstance(offers, dict) else "")
                    or odds_code(offers),
            "discount": discount,
        },
        "free_cash": {"amount": free_cash, "field": free_field},
        "extra_cash": {"amount": extra_cash, "field": extra_field},
        "wallet": {"amount": wallet, "field": wallet_field},
        "cashback": cashback,
        "to_pay": to_pay, "savings": savings,
        "lines": lines,
        "verified": any(value is not None for value in
                        (to_pay, item_total, delivery, discount, free_cash, extra_cash)),
    }


def extract_qr(payload: Any) -> dict:
    """Scannable payload out of a checkout/place response.

    UPI responses carry either a base64 PNG, a ``upi://`` intent string, or a
    plain text payload. All three are surfaced; the UI renders whichever exists.
    """
    image = text = intent = ""
    for node in _iter_dicts(payload):
        for key in ("qrCode", "qr_code", "qrImage", "qrString", "upiQr", "qrData",
                    "paymentQr", "qr"):
            value = node.get(key)
            if not isinstance(value, str) or not value.strip():
                continue
            value = value.strip()
            if value.startswith("iVBOR") or value.startswith("/9j/"):
                image = image or value
            elif value.lower().startswith(("upi://", "http://", "https://")):
                intent = intent or value
            else:
                text = text or value
        for key in ("upiIntent", "intentUri", "intentUrl", "upiLink", "paymentLink"):
            value = node.get(key)
            if isinstance(value, str) and value.strip():
                intent = intent or value.strip()
    return {"image": image, "text": text, "intent": intent,
            "present": bool(image or text or intent)}


def tracking_view(payload: Any) -> dict:
    """Order status + timeline + any link Swiggy put in the payload.

    ``dapi/order/trackV4`` returns a nested per-leg structure that is not
    documented; the walk below keeps every node carrying a status string and a
    time, which is what a tracking list is made of.
    """
    data = payload if isinstance(payload, dict) else {}
    inner = data.get("data") if isinstance(data.get("data"), dict) else data
    if not isinstance(inner, dict):
        inner = {}
    order = inner.get("order") if isinstance(inner.get("order"), dict) else inner
    status = str(_first(order, "orderStatus", "status", "statusText", "orderStatusText",
                        "deliveryStatus", default="") or "")
    status_text = str(_first(order, "statusMessage", "statusDescription",
                             "orderStatusMessage", default="") or "")
    eta = _first(order, "deliveryTime", "eta", "estimatedDeliveryTime",
                 "deliveryEta", "arrivalTime", default="")
    order_id = str(_first(order, "orderId", "order_id", "id", default="") or "")

    timeline: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for node in _iter_dicts(inner):
        label = _first(node, "title", "statusText", "status", "label", "description",
                       "state", "statusMessage")
        when = _first(node, "time", "timestamp", "createdAt", "updatedAt",
                      "displayTime", "date")
        if not isinstance(label, str) or not label.strip() or when is None:
            continue
        key = (label.strip()[:60], str(when)[:24])
        if key in seen:
            continue
        seen.add(key)
        timeline.append({"label": label.strip()[:80], "when": str(when)[:40],
                         "done": bool(node.get("completed") or node.get("done")
                                      or node.get("isCompleted"))})
        if len(timeline) >= 15:
            break

    links: list[str] = []
    for node in _iter_dicts(inner):
        for key in ("trackingUrl", "tracking_url", "shareableLink", "shareable_link",
                    "deeplink", "deepLink", "webUrl", "url"):
            value = node.get(key)
            if isinstance(value, str) and value.startswith("http") and value not in links:
                links.append(value[:400])
    return {"order_id": order_id, "status": status, "status_text": status_text,
            "eta": str(eta) if eta not in (None, "") else "",
            "timeline": timeline, "links": links[:5]}


class Fleet:
    def __init__(self, pool: ProxyPool) -> None:
        self.pool = pool
        self._locks: dict[str, threading.RLock] = {}
        self._locks_guard = threading.Lock()
        self._last_call: dict[str, float] = {}

    # ── plumbing ─────────────────────────────────────────────────────────────
    def lock(self, mobile: str) -> threading.RLock:
        with self._locks_guard:
            if mobile not in self._locks:
                self._locks[mobile] = threading.RLock()
            return self._locks[mobile]

    def _pace(self, mobile: str) -> None:
        """Small human gap between mutating calls on the same account."""
        last = self._last_call.get(mobile, 0.0)
        gap = random.uniform(config.PACE_MIN, config.PACE_MAX)
        elapsed = time.time() - last
        if elapsed < gap:
            time.sleep(gap - elapsed)
        self._last_call[mobile] = time.time()

    def record(self, mobile: str) -> dict:
        record = storage.get_session(mobile)
        if not record:
            raise KeyError(f"no stored session for {mobile}")
        return record

    def account(self, mobile: str) -> account_ops.Account:
        record = self.record(mobile)
        proxy = self.pool.resolve(self.pool.pick(mobile))
        return account_ops.Account(record, proxy=proxy, timeout=config.REQUEST_TIMEOUT)

    def _note(self, mobile: str, domain: str, result: dict) -> dict:
        status = int(result.get("status") or 0)
        if status in EXPIRED_CODES:
            storage.set_status(mobile, "EXPIRED")
            storage.activity("api", mobile, f"{domain}: HTTP {status} — session rejected")
        return result

    # ── liveness ─────────────────────────────────────────────────────────────
    def alive(self, mobile: str, force: bool = False) -> dict:
        record = self.record(mobile)
        if not force:
            checked = record.get("sessionStatusCheckedAt") or ""
            age = None
            try:
                age = time.time() - time.mktime(time.strptime(checked, "%Y-%m-%dT%H:%M:%SZ"))
            except (ValueError, TypeError):
                age = None
            if record.get("sessionStatus") in ("LIVE", "EXPIRED") and age is not None \
                    and 0 <= age < config.LIVENESS_TTL:
                return {"mobile": mobile, "status": record["sessionStatus"],
                        "cached": True, "checked_at": checked}

        with self.lock(mobile):
            self._pace(mobile)
            account = self.account(mobile)
            status = account.alive()
            patch = {"sessionStatusCheckedAt": storage.now_iso()}
            refreshed = False
            if status == "EXPIRED" and account.tid:
                renewed = account.refresh_login()
                if renewed.get("ok") and renewed.get("token") \
                        and renewed.get("token") != "UNREGISTERED_ACCOUNT":
                    patch.update({
                        "token": renewed["token"],
                        "sid": renewed.get("sid") or account.sid,
                        "tid": renewed.get("tid") or account.tid,
                        "customerId": renewed.get("customerId") or account.customer_id,
                    })
                    status = "LIVE"
                    refreshed = True
            patch["sessionStatus"] = status
            storage.update_session(mobile, patch)
            if status == "EXPIRED":
                self.pool.release(mobile)
            storage.activity("liveness", mobile,
                             f"{status}{' (refreshed via tid)' if refreshed else ''}")
            return {"mobile": mobile, "status": status, "cached": False,
                    "refreshed": refreshed, "checked_at": patch["sessionStatusCheckedAt"]}

    def check_many(self, mobiles: list[str]) -> list[dict]:
        targets = mobiles or [str(r.get("mobile", "")) for r in storage.list_sessions()]
        targets = [m for m in dict.fromkeys(targets) if m]
        if not targets:
            return []

        def work(mobile: str) -> dict:
            try:
                return self.alive(mobile, force=True)
            except Exception as exc:
                return {"mobile": mobile, "status": "ERROR", "error": str(exc)[:120]}

        with ThreadPoolExecutor(max_workers=config.CHECK_WORKERS) as pool:
            return list(pool.map(work, targets))

    # ── account snapshot ─────────────────────────────────────────────────────
    def overview(self, mobile: str) -> dict:
        with self.lock(mobile):
            self._pace(mobile)
            account = self.account(mobile)
            out: dict[str, Any] = {"mobile": mobile, "status": account.alive()}
            if out["status"] != "LIVE":
                storage.set_status(mobile, out["status"])
                out["error"] = "session not live — log in again"
                return out
            out["profile"] = self._thin(account.profile())
            out["wallet"] = self._thin(account.wallet())
            im_addresses = account.addresses("im")
            out["addresses"] = addresses(im_addresses)
            orders = account.orders(count=5, domain="im")
            out["orders"] = [account_ops.format_order_line(o)
                             for o in account_ops.extract_orders(orders)][:5]
            return out

    @staticmethod
    def _thin(result: dict) -> dict:
        payload = result.get("data")
        return {"ok": bool(result.get("ok")), "status": result.get("status"),
                "error": result.get("error"), "data": payload}

    # ── instamart ────────────────────────────────────────────────────────────
    def im_addresses(self, mobile: str) -> dict:
        with self.lock(mobile):
            result = self.account(mobile).addresses("im")
        return {"ok": result.get("ok"), "error": result.get("error"),
                "addresses": addresses(result), "raw": result.get("data")}

    def im_address_create(self, mobile: str, fields: dict) -> dict:
        required = ("fullAddress", "addressLine", "city", "postalCode",
                    "addressCategory", "userName", "userPhone")
        missing = [key for key in required if not str(fields.get(key) or "").strip()]
        if missing:
            return {"ok": False, "error": f"missing: {', '.join(missing)}", "status": 0}
        with self.lock(mobile):
            self._pace(mobile)
            result = self.account(mobile).create_address(
                full_address=str(fields.get("fullAddress")),
                address_line=str(fields.get("addressLine")),
                address_line2=str(fields.get("addressLine2") or ""),
                city=str(fields.get("city")),
                postal_code=str(fields.get("postalCode")),
                category=str(fields.get("addressCategory") or "OTHER"),
                user_name=str(fields.get("userName")),
                user_phone=str(fields.get("userPhone")),
                locality=str(fields.get("locality") or ""),
                tag=str(fields.get("addressTag") or ""),
                latitude=fields.get("latitude"),
                longitude=fields.get("longitude"),
                receiver_name=str(fields.get("receiverName") or ""),
                receiver_phone=str(fields.get("receiverPhone") or ""),
                domain=str(fields.get("domain") or "im"))
        created = addresses(result) if result.get("ok") else []
        if result.get("ok") and not created:
            # create_address answers {"addressId": "..."} with no address object,
            # so re-read the saved list and pick the new id out of it.
            payload = result.get("data")
            raw_id = ""
            if isinstance(payload, dict):
                raw_id = payload.get("addressId") or (payload.get("data") or {}).get("addressId") or ""
            if raw_id:
                try:
                    listing = addresses(self.account(mobile).addresses(
                        str(fields.get("domain") or "im")))
                except Exception:
                    listing = []
                created = [a for a in listing if a["id"] == str(raw_id)] or [{
                    "id": str(raw_id),
                    "label": str(fields.get("addressTag") or fields.get("addressCategory") or "address")[:40],
                    "line": str(fields.get("fullAddress") or "")[:160],
                    "tag": str(fields.get("addressTag") or "")[:40],
                    "lat": fields.get("latitude"),
                    "lng": fields.get("longitude"),
                }]
        storage.activity("address", mobile,
                         f"create → HTTP {result.get('status')} {created[0]['id'] if created else ''}".strip())
        return {"ok": result.get("ok"), "error": result.get("error"),
                "status": result.get("status"), "created": created,
                "raw": result.get("data")}

    def im_address_delete(self, mobile: str, address_id: str) -> dict:
        with self.lock(mobile):
            self._pace(mobile)
            account = self.account(mobile)
            result = account.delete_address(address_id, domain="im")
            if not result.get("ok") and "__" in address_id:
                # delete_address accepts the bare handle; the list gives a
                # signed one.
                result = account.delete_address(address_id.split("__")[0], domain="im")
        storage.activity("address", mobile, f"delete {address_id} → HTTP {result.get('status')}")
        return {"ok": result.get("ok"), "error": result.get("error"),
                "status": result.get("status"), "raw": result.get("data")}

    def im_go_to_items(self, mobile: str, address_id: str = "") -> dict:
        with self.lock(mobile):
            account = self.account(mobile)
            if not address_id:
                found = addresses(account.addresses("im"))
                if not found:
                    return {"ok": False, "error": "no delivery address on this account"}
                address_id = found[0]["id"]
            result = account.go_to_items(address_id)
        return {"ok": result.get("ok"), "error": result.get("error"),
                "address_id": address_id, "items": variants(result.get("data")),
                "raw": result.get("data")}

    # ── group (shared) cart ──────────────────────────────────────────────────
    def group_create(self, mobile: str, restaurant_id: str) -> dict:
        with self.lock(mobile):
            self._pace(mobile)
            result = self.account(mobile).group_cart_create(restaurant_id)
        storage.activity("group", mobile, f"create → HTTP {result.get('status')}")
        return {"ok": result.get("ok"), "error": result.get("error"),
                "status": result.get("status"), "raw": result.get("data")}

    def group_join(self, mobile: str, group_cart_id: str, restaurant_id: str = "") -> dict:
        with self.lock(mobile):
            self._pace(mobile)
            result = self.account(mobile).group_cart_join(group_cart_id, restaurant_id)
        storage.activity("group", mobile, f"join {group_cart_id} → HTTP {result.get('status')}")
        return {"ok": result.get("ok"), "error": result.get("error"),
                "status": result.get("status"), "raw": result.get("data")}

    def group_info(self, mobile: str, group_cart_id: str) -> dict:
        with self.lock(mobile):
            result = self.account(mobile).group_cart_info(group_cart_id)
        items = group_items(result.get("data"))
        return {"ok": result.get("ok"), "error": explain(result, "group cart read"),
                "status": result.get("status"), "items": items,
                "item_count": sum(i["quantity"] for i in items),
                "raw": result.get("data")}

    def group_leave(self, mobile: str, group_cart_id: str) -> dict:
        with self.lock(mobile):
            self._pace(mobile)
            result = self.account(mobile).group_cart_leave(group_cart_id)
        storage.activity("group", mobile, f"leave {group_cart_id} → HTTP {result.get('status')}")
        return {"ok": result.get("ok"), "error": result.get("error"),
                "status": result.get("status"), "raw": result.get("data")}

    def group_update(self, mobile: str, group_cart_id: str,
                     items: list[dict] | None = None, restaurant_id: str = "") -> dict:
        with self.lock(mobile):
            self._pace(mobile)
            result = self.account(mobile).group_cart_update(group_cart_id, items, restaurant_id)
        storage.activity("group", mobile, f"update {group_cart_id} → HTTP {result.get('status')}")
        return {"ok": result.get("ok"), "error": result.get("error"),
                "status": result.get("status"), "raw": result.get("data")}

    def im_search(self, mobile: str, query: str, address_id: str = "") -> dict:
        with self.lock(mobile):
            self._pace(mobile)
            account = self.account(mobile)
            if not address_id:
                found = addresses(account.addresses("im"))
                if not found:
                    return {"ok": False, "error": "no delivery address on this account"}
                address_id = found[0]["id"]
            result = account.search_products(query, address_id)
        return {"ok": result.get("ok"), "error": result.get("error"),
                "address_id": address_id,
                "items": variants(result.get("data")), "raw": result.get("data")}

    def im_cart(self, mobile: str) -> dict:
        with self.lock(mobile):
            result = self.account(mobile).cart("im")
        return {"ok": result.get("ok"), "error": result.get("error"), "raw": result.get("data")}

    def im_bill(self, mobile: str) -> dict:
        """Payable breakdown for the live Instamart cart."""
        with self.lock(mobile):
            result = self.account(mobile).cart("im")
        bill = bill_breakdown(result.get("data"))
        return {"ok": result.get("ok") and bill["verified"],
                "error": explain(result, "cart read") if not result.get("ok")
                         else (None if bill["verified"]
                               else "Swiggy returned a cart without a bill block — push the cart first"),
                **bill, "raw": result.get("data")}

    def im_set_cart(self, mobile: str, items: list[dict], address_id: str = "") -> dict:
        clean = []
        for item in items or []:
            spin = str(item.get("spinId") or "").strip()
            if not spin:
                continue
            quantity = max(1, int(item.get("quantity") or 1))
            entry = {"spinId": spin, "quantity": quantity}
            if item.get("skuId"):
                entry["skuId"] = str(item["skuId"])
            clean.append(entry)
        if not clean:
            return {"ok": False, "error": "cart is empty"}
        with self.lock(mobile):
            self._pace(mobile)
            account = self.account(mobile)
            if not address_id:
                found = addresses(account.addresses("im"))
                if found:
                    address_id = found[0]["id"]
            if not address_id:
                return {"ok": False, "error": "no delivery address on this account"}
            result = account.update_cart(clean, address_id)
        return {"ok": result.get("ok"), "error": result.get("error"),
                "sent": clean, "raw": result.get("data")}

    def im_clear_cart(self, mobile: str) -> dict:
        with self.lock(mobile):
            self._pace(mobile)
            result = self.account(mobile).clear_cart()
        return {"ok": result.get("ok"), "error": explain(result, "cart clear"),
                "raw": result.get("data")}

    def im_coupons(self, mobile: str, address_id: str = "") -> dict:
        """Coupons the live cart and the native cart are willing to show.

        The MCP tool list has no coupon tool, so this reads the dash cart view
        and the MCP cart and lifts every coupon-shaped node out of both.
        """
        with self.lock(mobile):
            account = self.account(mobile)
            if not address_id:
                found = addresses(account.addresses("im"))
                if found:
                    address_id = found[0]["id"]
            native = account.native_cart()
            mcp_cart = account.cart("im")
        rows = coupon_rows(native.get("data")) + coupon_rows(mcp_cart.get("data"))
        unique: list[dict] = []
        seen: set[str] = set()
        for row in rows:
            if row["code"] in seen:
                continue
            seen.add(row["code"])
            unique.append(row)
        return {"ok": bool(native.get("ok") or mcp_cart.get("ok")), "address_id": address_id,
                "coupons": unique[:30],
                "error": explain(native if not native.get("ok") else mcp_cart, "coupon list"),
                "raw": {"native": native.get("data"), "mcp": mcp_cart.get("data")}}

    def im_apply_coupon(self, mobile: str, address_id: str, code: str) -> dict:
        code = str(code or "").strip()
        if not code:
            return {"ok": False, "error": "a coupon code is required"}
        if not address_id:
            return {"ok": False, "error": "an address id is required — coupons are address-scoped"}
        with self.lock(mobile):
            self._pace(mobile)
            result = self.account(mobile).cart_apply_coupon(address_id, code)
        storage.activity("coupon", mobile, f"IM apply {code} → HTTP {result.get('status')}")
        return {"ok": result.get("ok"), "error": explain(result, f"coupon {code}"),
                "status": result.get("status"), "code": code,
                "raw": result.get("data")}

    def im_remove_coupon(self, mobile: str, address_id: str, code: str = "") -> dict:
        if not address_id:
            return {"ok": False, "error": "an address id is required"}
        with self.lock(mobile):
            self._pace(mobile)
            result = self.account(mobile).cart_remove_coupon(address_id, code)
        storage.activity("coupon", mobile, f"IM remove {code or 'all'} → HTTP {result.get('status')}")
        return {"ok": result.get("ok"), "error": explain(result, "coupon removal"),
                "status": result.get("status"), "raw": result.get("data")}

    def im_fillers(self, mobile: str, address_id: str = "",
                   max_price: float | None = None) -> dict:
        """Cheap line items so a cart can clear a minimum.

        Swiggy has no "₹1 store" endpoint in the dump, so this runs the filler
        queries and keeps every variant at or below ``max_price``. Price comes
        from the search payload, not from a hardcoded expectation.
        """
        ceiling = float(config.FILLER_MAX_PRICE if max_price is None else max_price)
        with self.lock(mobile):
            self._pace(mobile)
            account = self.account(mobile)
            if not address_id:
                found = addresses(account.addresses("im"))
                if not found:
                    return {"ok": False, "error": "no delivery address on this account",
                            "address_id": "", "items": [], "searched": []}
                address_id = found[0]["id"]
            hits: list[dict] = []
            seen: set[str] = set()
            searched: list[str] = []
            failure = None
            for query in config.FILLER_QUERIES:
                searched.append(query)
                result = account.search_products(query, address_id)
                if not result.get("ok"):
                    failure = failure or result
                for item in variants(result.get("data")):
                    price = item.get("price")
                    if price is None or float(price) > ceiling:
                        continue
                    if item["spinId"] in seen:
                        continue
                    seen.add(item["spinId"])
                    hits.append(item)
                if len(hits) >= 24:
                    break
        hits.sort(key=lambda item: (item.get("price") or 0, item["name"]))
        return {"ok": bool(hits) or failure is None, "address_id": address_id,
                "max_price": ceiling, "items": hits[:24], "searched": searched,
                "error": (None if hits else
                          (explain(failure, "filler search") if failure
                           else f"no items at or below ₹{ceiling:g} came back from the filler queries"))}

    def im_payments(self, mobile: str) -> dict:
        with self.lock(mobile):
            result = self.account(mobile).payment_options(domain="im")
        return {"ok": result.get("ok"), "error": result.get("error"), "raw": result.get("data")}

    def im_checkout(self, mobile: str, address_id: str, payment_method: str = "Cash",
                    intent_app: str = "", qr: bool = False,
                    confirm_duplicate: bool = False) -> dict:
        with self.lock(mobile):
            self._pace(mobile)
            result = self.account(mobile).checkout(
                address_id, payment_method=payment_method or "Cash",
                intent_app=intent_app or None, generate_qr=bool(qr),
                confirm_duplicate=bool(confirm_duplicate))
        storage.activity("order", mobile,
                         f"IM checkout {payment_method} → HTTP {result.get('status')}")
        return {"ok": result.get("ok"), "error": explain(result, "checkout"),
                "status": result.get("status"),
                "qr": extract_qr(result.get("data")),
                "raw": result.get("data")}

    def im_payment_status(self, mobile: str, paas_id: str, order_id: str = "",
                          address_id: str = "", cart_id: str = "") -> dict:
        with self.lock(mobile):
            result = self.account(mobile).check_payment_status(
                paas_id, order_id=order_id or None, address_id=address_id or None,
                cart_id=cart_id or None)
        return {"ok": result.get("ok"), "error": result.get("error"),
                "status": result.get("status"), "raw": result.get("data")}

    def im_confirm(self, mobile: str, order_id: str, transaction_id: str = "",
                   paas_id: str = "", address_id: str = "", cart_id: str = "") -> dict:
        with self.lock(mobile):
            self._pace(mobile)
            result = self.account(mobile).confirm_order(
                order_id, transaction_id=transaction_id or None,
                paas_id=paas_id or None, address_id=address_id or None,
                cart_id=cart_id or None)
        storage.activity("order", mobile, f"IM confirm {order_id} → HTTP {result.get('status')}")
        return {"ok": result.get("ok"), "error": result.get("error"),
                "status": result.get("status"), "raw": result.get("data")}

    def im_orders(self, mobile: str, count: int = 15, active_only: bool = False) -> dict:
        with self.lock(mobile):
            result = self.account(mobile).orders(count=count, domain="im",
                                                 active_only=active_only)
        rows = account_ops.extract_orders(result)
        return {"ok": result.get("ok"), "error": result.get("error"),
                "orders": rows, "lines": [account_ops.format_order_line(o) for o in rows],
                "raw": result.get("data")}

    def im_track(self, mobile: str, order_id: str, lat: float, lng: float) -> dict:
        with self.lock(mobile):
            result = self.account(mobile).track_order(order_id, lat, lng)
        return {"ok": result.get("ok"), "error": result.get("error"), "raw": result.get("data")}

    # ── food ─────────────────────────────────────────────────────────────────
    def food_addresses(self, mobile: str) -> dict:
        with self.lock(mobile):
            result = self.account(mobile).addresses("food")
        return {"ok": result.get("ok"), "error": result.get("error"),
                "addresses": addresses(result), "raw": result.get("data")}

    def food_menu(self, mobile: str, restaurant_id: str, address_id: str = "",
                  lat: float | None = None, lng: float | None = None,
                  page: int = 1) -> dict:
        with self.lock(mobile):
            self._pace(mobile)
            result = self.account(mobile).food_menu(restaurant_id, address_id,
                                                   lat, lng, page=page)
        return {"ok": result.get("ok"), "error": result.get("error"),
                "items": account_ops.extract_food_items(result), "raw": result.get("data")}

    def food_search_restaurants(self, mobile: str, query: str,
                                address_id: str = "") -> dict:
        with self.lock(mobile):
            self._pace(mobile)
            result = self.account(mobile).search_restaurants(query, address_id)
        rows = []
        for node in _iter_dicts(result.get("data")):
            rid = node.get("id") or node.get("restaurantId")
            name = node.get("name")
            if not rid or not name:
                continue
            if any(r["id"] == str(rid) for r in rows):
                continue
            rows.append({
                "id": str(rid),
                "name": str(name)[:90],
                "cuisines": ", ".join(node.get("cuisines") or [])[:70]
                            if isinstance(node.get("cuisines"), list) else str(node.get("cuisines") or "")[:70],
                "rating": node.get("avgRating"),
                "area": node.get("areaName") or node.get("locality") or "",
                "cost_for_two": node.get("costForTwo") or "",
                "lat": node.get("latitude") or node.get("lat"),
                "lng": node.get("longitude") or node.get("lng"),
            })
            if len(rows) >= 30:
                break
        return {"ok": result.get("ok"), "error": result.get("error"),
                "restaurants": rows, "raw": result.get("data")}

    def food_search_menu(self, mobile: str, query: str, address_id: str = "") -> dict:
        with self.lock(mobile):
            self._pace(mobile)
            result = self.account(mobile).search_menu(query, address_id)
        return {"ok": result.get("ok"), "error": result.get("error"),
                "items": account_ops.extract_food_items(result), "raw": result.get("data")}

    def food_cart(self, mobile: str, address_id: str) -> dict:
        with self.lock(mobile):
            result = self.account(mobile).food_cart(address_id)
        return {"ok": result.get("ok"), "error": result.get("error"),
                **cart_summary(result.get("data")), "raw": result.get("data")}

    def food_set_cart(self, mobile: str, address_id: str, restaurant_id: str,
                      items: list[dict], restaurant_name: str = "",
                      cutlery: bool = False) -> dict:
        cart_items = []
        for item in items or []:
            item_id = item.get("id") or item.get("menu_item_id")
            if not item_id:
                continue
            row = {"menu_item_id": str(item_id),
                   "quantity": int(item.get("quantity") or 1)}
            if item.get("variants"):
                row["variants"] = item["variants"]
            if item.get("variantsV2"):
                row["variantsV2"] = item["variantsV2"]
            cart_items.append(row)
        if not cart_items:
            return {"ok": False, "error": "cart is empty"}
        with self.lock(mobile):
            self._pace(mobile)
            result = self.account(mobile).update_food_cart(
                restaurant_id, address_id, cart_items,
                restaurant_name=restaurant_name, cutlery=cutlery)
        return {"ok": result.get("ok"), "error": result.get("error"),
                **cart_summary(result.get("data")), "raw": result.get("data")}

    def food_flush(self, mobile: str) -> dict:
        with self.lock(mobile):
            self._pace(mobile)
            result = self.account(mobile).flush_food_cart()
        storage.activity("cart", mobile, f"Food cart flushed → {result.get('ok')}")
        return {"ok": result.get("ok"), "error": result.get("error"),
                "raw": result.get("data")}

    def food_coupons(self, mobile: str, address_id: str, restaurant_id: str,
                     code: str = "") -> dict:
        with self.lock(mobile):
            result = self.account(mobile).fetch_food_coupons(address_id, restaurant_id,
                                                            coupon_code=code)
        return {"ok": result.get("ok"),
                "error": explain(result, "coupon fetch"),
                "coupons": coupon_rows(result.get("data"), limit=25),
                "raw": result.get("data")}

    def food_apply_coupon(self, mobile: str, address_id: str, code: str,
                          cart_id: str | int | None = None) -> dict:
        with self.lock(mobile):
            self._pace(mobile)
            result = self.account(mobile).apply_food_coupon(address_id, code,
                                                            cart_id=cart_id)
        return {"ok": result.get("ok"), "error": result.get("error"),
                **cart_summary(result.get("data")), "raw": result.get("data")}

    def food_payments(self, mobile: str, address_id: str,
                      cart_amount: float | None = None) -> dict:
        with self.lock(mobile):
            result = self.account(mobile).payment_options(
                address_id=address_id, domain="food", cart_amount=cart_amount)
        data = result.get("data") or {}
        methods = []
        if isinstance(data, dict):
            for row in data.get("allMethods") or []:
                if not isinstance(row, dict):
                    continue
                methods.append({
                    "id": row.get("id"),
                    "group": row.get("groupName") or "",
                    "label": row.get("displayName") or row.get("id") or "method",
                    "enabled": bool(row.get("enabled", True)),
                })
            cod = data.get("cod") or {}
            if cod.get("available"):
                methods.append({"id": cod.get("id") or "COD", "group": "Cash",
                                "label": cod.get("displayName") or "Pay on delivery",
                                "enabled": True})
            wallet = data.get("swiggyMoney") or {}
            if wallet.get("available"):
                methods.append({"id": wallet.get("id") or "SwiggyPay", "group": "Wallet",
                                "label": wallet.get("displayName") or "Swiggy Money",
                                "enabled": True})
        return {"ok": result.get("ok"), "error": result.get("error"),
                "methods": methods, "raw": data}

    def food_place(self, mobile: str, address_id: str,
                   payment_method: str = "COD", intent_app: str = "",
                   generate_qr: bool = False, note: str = "") -> dict:
        with self.lock(mobile):
            self._pace(mobile)
            result = self.account(mobile).place_food_order_mcp(
                address_id, payment_method=payment_method,
                intent_app=intent_app or None, generate_qr=generate_qr, note=note)
        data = result.get("data") if isinstance(result.get("data"), dict) else {}
        order_id = (data.get("orderId") or data.get("order_id")
                    or (data.get("data") or {}).get("orderId")
                    if isinstance(data, dict) else None)
        paas_id = (data.get("paasId") or data.get("paas_id")
                   or (data.get("data") or {}).get("paasId")
                   if isinstance(data, dict) else None)
        storage.activity("order", mobile,
                         f"Food place {payment_method} → {order_id or result.get('error')}")
        return {"ok": result.get("ok"), "error": explain(result, "place order"),
                "order_id": order_id, "paas_id": paas_id,
                "qr": extract_qr(data),
                "status": data.get("status") or data.get("statusMessage"),
                "raw": data}

    def food_confirm(self, mobile: str, order_id: str, transaction_id: str = "",
                     paas_id: str = "", address_id: str = "",
                     cart_id: str = "") -> dict:
        with self.lock(mobile):
            self._pace(mobile)
            result = self.account(mobile).confirm_order(
                order_id, transaction_id=transaction_id or None,
                paas_id=paas_id or None, address_id=address_id or None,
                cart_id=cart_id or None, domain="food")
        storage.activity("order", mobile, f"Food confirm {order_id} → {result.get('ok')}")
        return {"ok": result.get("ok"), "error": result.get("error"),
                "raw": result.get("data")}

    def food_payment_status(self, mobile: str, paas_id: str, order_id: str = "",
                            address_id: str = "", cart_id: str = "") -> dict:
        with self.lock(mobile):
            result = self.account(mobile).check_payment_status(
                paas_id, order_id=order_id or None, address_id=address_id or None,
                cart_id=cart_id or None, domain="food")
        return {"ok": result.get("ok"), "error": result.get("error"),
                "raw": result.get("data")}

    def food_orders(self, mobile: str, count: int = 15, address_id: str = "") -> dict:
        with self.lock(mobile):
            result = self.account(mobile).orders(count=count, domain="food",
                                                 address_id=address_id)
            rows = account_ops.extract_orders(result)
            if not rows and address_id:
                native = self.account(mobile).order_history_native(count=count,
                                                                  order_type="DASH")
                rows = account_ops.extract_orders(native)
                if rows:
                    result = native
        return {"ok": result.get("ok"), "error": explain(result, "order history"),
                "orders": rows, "lines": [account_ops.format_order_line(o) for o in rows],
                "raw": result.get("data")}

    def food_bill(self, mobile: str, address_id: str) -> dict:
        """Payable breakdown after coupon + free cash + extra cash + wallet."""
        if not address_id:
            return {"ok": False, "error": "an address id is required"}
        with self.lock(mobile):
            result = self.account(mobile).food_cart(address_id)
        bill = bill_breakdown(result.get("data"))
        return {"ok": result.get("ok") and bill["verified"],
                "error": explain(result, "cart read") if not result.get("ok")
                         else (None if bill["verified"]
                               else "Swiggy returned a cart without a bill block — push the cart first"),
                **bill, "raw": result.get("data")}

    def food_track(self, mobile: str, order_id: str) -> dict:
        """Tracking timeline for a food order plus any shareable link Swiggy hands back."""
        order_id = str(order_id or "").strip()
        if not order_id:
            return {"ok": False, "error": "an order id is required"}
        with self.lock(mobile):
            self._pace(mobile)
            account = self.account(mobile)
            track = account.order_track(order_id)
            view = tracking_view(track.get("data"))
            if not view["timeline"] and not view["status"]:
                fallback = account.order_track_v2(order_id)
                alt = tracking_view(fallback.get("data"))
                if alt["timeline"] or alt["status"]:
                    track, view = fallback, alt
            links = list(view["links"])
            share = account.order_shareable_link(order_id)
            share_view = tracking_view(share.get("data"))
            for link in share_view["links"]:
                if link not in links:
                    links.append(link)
        storage.activity("order", mobile, f"track {order_id} → HTTP {track.get('status')}")
        return {"ok": bool(track.get("ok") and (view["timeline"] or view["status"])),
                "error": (None if track.get("ok") else explain(track, "order tracking")),
                **view, "links": links[:6],
                "raw": {"track": track.get("data"), "share": share.get("data")}}

    # ── wallet / offers ──────────────────────────────────────────────────────
    def wallet(self, mobile: str) -> dict:
        with self.lock(mobile):
            account = self.account(mobile)
            balance = account.wallet()
            eligibility = account.wallet_eligibility()
        return {"ok": balance.get("ok"),
                "balance": balance.get("available"),
                "balance_fmt": balance.get("available_fmt"),
                "eligibility_ok": eligibility.get("ok"),
                "eligibility": eligibility.get("data"),
                "raw": balance.get("data")}

    def wallet_statement(self, mobile: str, count: int = 20) -> dict:
        with self.lock(mobile):
            result = self.account(mobile).wallet_statement(count=count)
        return {"ok": result.get("ok"), "error": result.get("error"), "raw": result.get("data")}

    def claim_gift_card(self, mobile: str, code: str, secret: str) -> dict:
        with self.lock(mobile):
            self._pace(mobile)
            result = self.account(mobile).claim_gift_card(code.strip().upper(), secret.strip())
        storage.activity("wallet", mobile, f"gift card claim → HTTP {result.get('status')}")
        return {"ok": result.get("ok"), "error": result.get("error"),
                "status": result.get("status"), "raw": result.get("data")}

    def food_offers(self, mobile: str, address_id: str, restaurant_id: str) -> dict:
        with self.lock(mobile):
            result = self.account(mobile).fetch_food_coupons(address_id, restaurant_id)
        coupons = []
        for node in _iter_dicts(result.get("data")):
            code = node.get("couponCode") or node.get("code")
            if not isinstance(code, str) or not code:
                continue
            if any(c["code"] == code for c in coupons):
                continue
            coupons.append({"code": code,
                            "title": str(node.get("couponDescription")
                                         or node.get("description") or "")[:120]})
        return {"ok": result.get("ok"), "error": result.get("error"),
                "coupons": coupons[:20], "raw": result.get("data")}

    def payment_offers(self, mobile: str, lat: float, lng: float,
                       restaurant_id: str = "", cart_value: int = 0) -> dict:
        with self.lock(mobile):
            result = self.account(mobile).payment_offers(lat, lng, restaurant_id, cart_value)
        rows = payment_rows(result.get("data"))
        return {"ok": result.get("ok"), "error": explain(result, "payment offers"),
                "offers": rows, "by_method": _group_offers(rows),
                "raw": result.get("data")}

    def offers_list(self, mobile: str) -> dict:
        with self.lock(mobile):
            result = self.account(mobile).offers_v2()
        return {"ok": result.get("ok"), "error": result.get("error"), "raw": result.get("data")}

    def scratch(self, mobile: str, action: str, payload: dict | None = None) -> dict:
        with self.lock(mobile):
            self._pace(mobile)
            account = self.account(mobile)
            result = (account.scratch_assign(payload or {}) if action == "assign"
                      else account.scratch_unlock(payload or {}))
        return {"ok": result.get("ok"), "error": result.get("error"), "raw": result.get("data")}

    def set_geo(self, mobile: str, latitude: float, longitude: float) -> dict:
        """Pin the position hint every native call carries for this account."""
        storage.update_session(mobile, {"latitude": float(latitude),
                                        "longitude": float(longitude)})
        storage.activity("session", mobile, f"geo {latitude},{longitude}")
        return {"mobile": mobile, "latitude": float(latitude), "longitude": float(longitude)}

    def refresh(self, mobile: str) -> dict:
        with self.lock(mobile):
            self._pace(mobile)
            account = self.account(mobile)
            result = account.refresh_login()
        if result.get("ok") and result.get("token"):
            storage.update_session(mobile, {
                "token": result["token"],
                "sid": result.get("sid") or "",
                "tid": result.get("tid") or "",
                "customerId": result.get("customerId") or "",
                "sessionStatus": "LIVE",
                "sessionStatusCheckedAt": storage.now_iso(),
            })
            storage.activity("liveness", mobile, "token re-minted from tid")
        return {"ok": bool(result.get("ok")), "error": result.get("error"),
                "token": bool(result.get("token")), "raw": result.get("data")}
