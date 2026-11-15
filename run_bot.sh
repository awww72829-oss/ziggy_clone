#!/usr/bin/env bash
cd "$(dirname "$0")"
echo "🚀 Starting Swiggy Telegram Bot..."
# caffeinate -i prevents macOS from sleeping while bot runs
# -i = prevent idle sleep, -s = prevent system sleep
caffeinate -is python3 swiggy_bot.py

