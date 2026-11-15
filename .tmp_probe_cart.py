import account_ops as A, json, warnings
warnings.filterwarnings('ignore')
rec = next(r for r in json.load(open('sessions.json')) if r.get('mobile') == '9173524896')
rec = {**rec, 'latitude': '30.9010', 'longitude': '75.8573'}
a = A.Account(rec)
aid = 'dbriotk1d96ql6s4bg60__AdfqOASFI-wotlBUcVmGel'
rid = '70941'

r = a._mcp('food', 'update_food_cart', {
    "restaurantId": rid,
    "addressId": aid,
    "cartItems": [{"menu_item_id": "159452529", "quantity": 1}],
})
print('update ok', r.get('ok'), 'err', str(r.get('error'))[:300])
print(json.dumps(r.get('data'), indent=1)[:1800])
print()
c = a.food_cart(aid)
print('get cart ok', c.get('ok'), 'err', str(c.get('error'))[:200])
print(json.dumps(c.get('data'), indent=1)[:1800])
