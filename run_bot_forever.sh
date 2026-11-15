#!/usr/bin/env bash
# Runs bot forever with auto-restart + prevents Mac from sleeping
# Usage: ./run_bot_forever.sh
cd "$(dirname "$0")"

# Keep display + system awake the whole time
caffeinate -is &
CAFF_PID=$!

cleanup() {
    echo "🛑 Stopping caffeinate (PID $CAFF_PID)..."
    kill $CAFF_PID 2>/dev/null
    exit 0
}
trap cleanup SIGINT SIGTERM

echo "☕ caffeinate active (system will not sleep)"
echo "🔄 Auto-restart loop enabled"
echo ""

RESTART_DELAY=5

while true; do
    echo "🚀 $(date '+%Y-%m-%d %H:%M:%S') — Starting bot..."
    python3 swiggy_bot.py
    EXIT_CODE=$?
    if [ $EXIT_CODE -eq 0 ]; then
        echo "👋 Bot exited cleanly. Stopping."
        break
    fi
    echo "⚠️  Bot crashed (exit $EXIT_CODE). Restarting in ${RESTART_DELAY}s..."
    sleep $RESTART_DELAY
done

kill $CAFF_PID 2>/dev/null

