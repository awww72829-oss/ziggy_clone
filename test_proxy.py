"""Quick SOCKS5H proxy test"""
import requests
import urllib3
urllib3.disable_warnings()

PROXY = "socks5h://res-in:pgw-a8a6746af4a9ee6b11c95a88450b7d72760797c3ae2a41aa@gw.proxyrise.com:443"
proxies = {"http": PROXY, "https": PROXY}

print("Testing SOCKS5H proxy...")

try:
    r = requests.get("https://api.ipify.org", proxies=proxies, timeout=15)
    print(f"[HTTPS ipify] Status: {r.status_code} | IP: {r.text.strip()}")
except Exception as e:
    print(f"[HTTPS ipify] FAILED: {e}")

try:
    r = requests.get("https://profile.swiggy.com/api/v3/app/sms_otp?mobile=9999999999",
                     proxies=proxies, timeout=15)
    print(f"[HTTPS Swiggy] Status: {r.status_code} | Body: {r.text[:200]}")
except Exception as e:
    print(f"[HTTPS Swiggy] FAILED: {e}")
