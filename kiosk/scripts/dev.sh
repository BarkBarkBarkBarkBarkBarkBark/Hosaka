#!/usr/bin/env bash
# Hosaka kiosk dev runner — one command, two processes.
#
#   cd kiosk && npm run dev
#
# Spawns the Vite dev server in the background, waits for it to come up,
# then launches Electron in windowed mode pointed at the dev server. SPA
# edits hot-reload inside the kiosk window. Ctrl-C kills both.
set -euo pipefail

KIOSK_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FRONTEND_DIR="$(cd "$KIOSK_DIR/../frontend" && pwd)"

VITE_PORT="${VITE_PORT:-5173}"
VITE_URL="http://localhost:${VITE_PORT}"
VITE_LOG="${TMPDIR:-/tmp}/hosaka-vite-${VITE_PORT}.log"

have_cmd() {
    command -v "$1" >/dev/null 2>&1
}

port_listener_pids() {
    local port="$1"
    if have_cmd lsof; then
        lsof -tiTCP:"$port" -sTCP:LISTEN 2>/dev/null | awk '!seen[$0]++'
        return 0
    fi
    if have_cmd ss; then
        ss -ltnp "sport = :$port" 2>/dev/null \
            | sed -n 's/.*pid=\([0-9][0-9]*\).*/\1/p' \
            | awk '!seen[$0]++'
        return 0
    fi
    return 1
}

port_is_busy() {
    local port="$1"
    [[ -n "$(port_listener_pids "$port" || true)" ]]
}

print_port_busy_help() {
    echo "[kiosk dev] port :$VITE_PORT is already in use." >&2
    echo "[kiosk dev] try one of:" >&2
    echo "[kiosk dev]   hosaka dev         # reuse/open the existing session" >&2
    echo "[kiosk dev]   hosaka dev -fresh  # stop the listener, then relaunch" >&2
    echo "[kiosk dev]   hosaka down        # stop local dev processes cleanly" >&2
}

# Ensure frontend deps are installed — npm run dev assumes they are.
if [ ! -d "$FRONTEND_DIR/node_modules" ]; then
    echo "[kiosk dev] installing frontend deps…"
    (cd "$FRONTEND_DIR" && npm install)
fi
if [ ! -d "$KIOSK_DIR/node_modules" ]; then
    echo "[kiosk dev] installing kiosk deps…"
    (cd "$KIOSK_DIR" && npm install)
fi

cleanup() {
    # Kill the entire process group on Ctrl-C / exit so vite doesn't survive.
    if [ -n "${VITE_PID:-}" ] && kill -0 "$VITE_PID" 2>/dev/null; then
        kill "$VITE_PID" 2>/dev/null || true
    fi
    if [ -n "${TAIL_PID:-}" ] && kill -0 "$TAIL_PID" 2>/dev/null; then
        kill "$TAIL_PID" 2>/dev/null || true
    fi
    pkill -P $$ 2>/dev/null || true
}
trap cleanup EXIT INT TERM

if port_is_busy "$VITE_PORT"; then
    print_port_busy_help
    exit 1
fi

echo "[kiosk dev] starting vite on :$VITE_PORT"
(cd "$FRONTEND_DIR" && npm run dev -- --port "$VITE_PORT" --strictPort) >"$VITE_LOG" 2>&1 &
VITE_PID=$!

# Wait for vite to respond (up to ~30 s).
for i in $(seq 1 60); do
    if curl -sf "$VITE_URL" >/dev/null 2>&1; then
        break
    fi
    if ! kill -0 "$VITE_PID" 2>/dev/null; then
        if port_is_busy "$VITE_PORT"; then
            print_port_busy_help
        else
            echo "[kiosk dev] vite exited before coming up — aborting." >&2
            echo "[kiosk dev] recent log output:" >&2
            sed -n '1,20p' "$VITE_LOG" >&2 || true
        fi
        exit 1
    fi
    sleep 0.5
done

tail -n +1 -f "$VITE_LOG" &
TAIL_PID=$!

echo "[kiosk dev] launching electron → $VITE_URL"
cd "$KIOSK_DIR"
HOSAKA_KIOSK_URL="$VITE_URL" \
HOSAKA_KIOSK_FULLSCREEN=0 \
HOSAKA_KIOSK_DEVTOOLS="${HOSAKA_KIOSK_DEVTOOLS:-1}" \
    npx electron .
