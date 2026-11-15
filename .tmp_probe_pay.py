import account_ops as A, json, warnings
warnings.filterwarnings('ignore')
rec = next(r for r in json.load(open('sessions.json')) if r.get('mobile') == '9173524896')
rec = {**rec, 'latitude': '30.9010', 'longitude': '75.8573'}
a = A.Account(rec)
aid = 'dbriotk1d96ql6s4bg60__AdfqOASFI-wotlBUcVmGel'
rid = '70941'

c = a._mcp('food', 'fetch_food_coupons', {"restaurantId": rid, "addressId": aid})
print('coupons ok', c.get('ok'), 'err', str(c.get('error'))[:200])
print(json.dumps(c.get('data'), indent=1)[:1400])
print()

p = a._mcp('food', 'get_payment_options', {"addressId": aid, "cartAmount": 135})
print('payments ok', p.get('ok'), 'err', str(p.get('error'))[:200])
print(json.dumps(p.get('data'), indent=1)[:1600])
