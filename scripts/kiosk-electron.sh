#!/usr/bin/env bash
# Launch the Hosaka Electron kiosk against the local FastAPI webserver.
#
# Used by:
#   - systemd/hosaka-kiosk.service (system boot)
#   - dotfiles/openbox/autostart    (X session start)
#
# Responsibilities:
#   1. Wait for hosaka-webserver.service to answer on 127.0.0.1:8421.
#   2. Locate the project's electron binary (kiosk/node_modules/.bin).
#   3. Bias OOM killer toward the kiosk so a runaway Chromium tab can
#      never take out the SSH session on a thrashing Pi 3B.
#   4. exec into electron, handing it the local FastAPI URL so the SPA
#      has first-class access to /api/* and matching-origin cookies.
#
# Env overrides:
#   HOSAKA_REPO              path to the Hosaka checkout
#                            (defaults to /opt/hosaka-field-terminal, then ~/Hosaka)
#   HOSAKA_KIOSK_URL         override the URL the kiosk loads
#   HOSAKA_KIOSK_FULLSCREEN  "0" for windowed dev runs
set -euo pipefail

log() { echo "[kiosk-electron] $*" >&2; }

# ── repo root ─────────────────────────────────────────────────────────────
HOSAKA_REPO="${HOSAKA_REPO:-}"
if [ -z "$HOSAKA_REPO" ]; then
    for candidate in "/opt/hosaka-field-terminal" "$HOME/Hosaka"; do
        if [ -d "$candidate/kiosk" ]; then
            HOSAKA_REPO="$candidate"
            break
        fi
    done
fi
if [ -z "$HOSAKA_REPO" ] || [ ! -d "$HOSAKA_REPO/kiosk" ]; then
    log "cannot find Hosaka checkout (set HOSAKA_REPO)"
    exit 2
fi

KIOSK_DIR="$HOSAKA_REPO/kiosk"
ELECTRON_BIN="$KIOSK_DIR/node_modules/.bin/electron"

# ── deps ──────────────────────────────────────────────────────────────────
if [ ! -x "$ELECTRON_BIN" ]; then
    log "electron not found — running npm install in $KIOSK_DIR"
    # NOTE: electron is declared in devDependencies (that's the conventional
    # place for it), but we absolutely need it at runtime — it IS the runtime.
    # Do not pass --omit=dev here; it would skip the binary we're trying to
    # install.
    (cd "$KIOSK_DIR" && npm install --no-fund --no-audit)
fi

# postinstall sometimes fails silently on a thrashing Pi (network blip, SD
# card EIO). Detect and retry once before we give up.
if [ ! -d "$KIOSK_DIR/node_modules/electron/dist" ]; then
    log "electron/dist missing — re-running postinstall"
    (cd "$KIOSK_DIR" && node node_modules/electron/install.js) || {
        log "electron postinstall failed; cannot start kiosk"
        exit 1
    }
fi

# ── wait for FastAPI ──────────────────────────────────────────────────────
TARGET_URL="${HOSAKA_KIOSK_URL:-http://127.0.0.1:8421/}"
HEALTH_URL="${TARGET_URL%/}/api/health"
for i in $(seq 1 60); do
    if curl -sf "$HEALTH_URL" >/dev/null 2>&1; then
        break
    fi
    sleep 1
done

# ── OOM bias ──────────────────────────────────────────────────────────────
# Bias the electron process HIGH for the OOM killer, matching the old
# Chromium launcher. SSH keeps priority over the UI.
echo 800 > /proc/self/oom_score_adj 2>/dev/null || true

export HOSAKA_KIOSK_URL="$TARGET_URL"
export HOSAKA_KIOSK_FULLSCREEN="${HOSAKA_KIOSK_FULLSCREEN:-1}"

log "launching: $ELECTRON_BIN . (url=$HOSAKA_KIOSK_URL fullscreen=$HOSAKA_KIOSK_FULLSCREEN)"
cd "$KIOSK_DIR"
exec "$ELECTRON_BIN" . --no-sandbox
