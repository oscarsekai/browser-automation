#!/usr/bin/env bash
# Start a dedicated Chrome instance for browser-automation CDP scraping.
# Usage: ./scripts/start_chrome.sh
#        PORT=9334 ./scripts/start_chrome.sh   # override port

set -euo pipefail

PORT="${PORT:-9333}"
PROFILE="${CHROME_USER_DATA_DIR:-$HOME/chrome-hermes-profile}"
CHROME="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

mkdir -p "$PROFILE"

# Kill existing Chrome on this port if already running
EXISTING_PID=$(ps -ax -o pid=,command= 2>/dev/null \
  | awk "/--remote-debugging-port=${PORT}/ && /Google Chrome/ && !/Helper/ { print \$1 }" \
  | head -1)

if [[ -n "$EXISTING_PID" ]]; then
  echo "[chrome] killing existing Chrome PID $EXISTING_PID on port $PORT"
  kill "$EXISTING_PID" 2>/dev/null || true
  sleep 2
fi

echo "[chrome] launching Chrome on port $PORT with profile $PROFILE"
"$CHROME" \
  --remote-debugging-port="$PORT" \
  --user-data-dir="$PROFILE" \
  --no-first-run \
  --no-default-browser-check \
  --disable-default-apps \
  &

# Wait for CDP to be ready
echo -n "[chrome] waiting for CDP..."
for i in $(seq 1 25); do
  if nc -z localhost "$PORT" 2>/dev/null; then
    echo " ready (${i}s)"
    exit 0
  fi
  sleep 1
  echo -n "."
done

echo ""
echo "[chrome] WARNING: CDP port $PORT not ready after 25s — Chrome may still be starting"
