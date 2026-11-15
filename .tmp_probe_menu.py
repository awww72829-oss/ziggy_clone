import account_ops as A, json, warnings
warnings.filterwarnings('ignore')
rec = next(r for r in json.load(open('sessions.json')) if r.get('mobile') == '9173524896')
a = A.Account(rec)
h = {
    "Authorization": f"Bearer {a.token}",
    "Content-Type": "application/json",
    "Accept": "application/json, text/event-stream",
    "User-Agent": a.user_agent,
    "tid": a.tid,
    "sid": a.sid,
    "deviceId": a.device_id,
    "latitude": a.latitude,
    "longitude": a.longitude,
}
h = {k: v for k, v in h.items() if v}
r = a._session().post(A.MCP_FOOD, headers=h, json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}, timeout=40)
tools = {t['name']: t for t in r.json()['result']['tools']}
for name in ('update_food_cart', 'flush_food_cart', 'get_food_cart', 'place_food_order',
             'fetch_food_coupons', 'apply_food_coupon', 'get_payment_options',
             'check_payment_status', 'confirm_order'):
    t = tools.get(name)
    if not t:
        print(name, 'MISSING')
        continue
    sch = t.get('inputSchema') or {}
    props = list((sch.get('properties') or {}).keys())
    print(f"{name}: {props}  required={sch.get('required')}")
print()
print(json.dumps(tools['update_food_cart'].get('inputSchema'), indent=1)[:2500])
