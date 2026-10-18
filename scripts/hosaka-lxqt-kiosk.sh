#!/usr/bin/env bash
# Shared TUI + Menu host supervisor for LXQt and Openbox sessions.
#
# LXQt is the base desktop (see ~/.xinitrc + `hosaka mode`). This script is run
# once per LXQt login via ~/.config/autostart/hosaka-kiosk.desktop. It brings up
# the Hosaka SPA fullscreen on top of LXQt and keeps it alive, so "Hosaka" is
# what the operator sees at boot while the flatpak desktop sits one toggle away.
#
# Toggling to the desktop does NOT exit Electron. `hosaka mode desktop`, the
# Super+H shortcut, and the in-SPA button just hide/show the window (see the
# SIGUSR1/SIGUSR2 handlers in kiosk/main.js), so closing a launched flatpak app
# lands you straight back in Hosaka instead of a bare desktop.
set -u

HOSAKA_MODE_FILE="${HOSAKA_STATE_DIR:-/var/lib/hosaka}/mode"
HOSAKA_BOOT_MARK="/boot/firmware/hosaka-build-mode"
LOG="${HOSAKA_KIOSK_LOG:-/tmp/hosaka-lxqt-kiosk.log}"
ELECTRON_LAUNCHER="${HOSAKA_KIOSK_LAUNCHER:-/usr/local/bin/hosaka-kiosk-electron}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" 2>/dev/null && pwd)"
BRANDING_SCRIPT="${HOSAKA_DESKTOP_BRANDING:-}"
if [ -z "$BRANDING_SCRIPT" ]; then
  for candidate in /usr/local/bin/hosaka-apply-desktop-branding "$SCRIPT_DIR/hosaka-apply-desktop-branding.sh"; do
    [ -x "$candidate" ] && { BRANDING_SCRIPT="$candidate"; break; }
  done
fi

# Fullscreen-on-top is the whole point of booting into Hosaka over LXQt.
export HOSAKA_KIOSK_FULLSCREEN="${HOSAKA_KIOSK_FULLSCREEN:-1}"
export HOSAKA_KIOSK_URL="${HOSAKA_KIOSK_URL:-http://127.0.0.1:8421/}"

log() { printf '%s %s\n' "$(date '+%H:%M:%S')" "$*" >>"$LOG" 2>/dev/null || true; }

is_device_mode() {
  local m=""
  [ -f "$HOSAKA_MODE_FILE" ] && m="$(cat "$HOSAKA_MODE_FILE" 2>/dev/null)"
  case "$m" in
    device|build) return 0 ;;
    console|kiosk) return 1 ;;
    *) [ -f "$HOSAKA_BOOT_MARK" ] && return 0 || return 1 ;;
  esac
}

# Device mode owns tty1 with the diagnostic dashboard; don't launch the kiosk.
if is_device_mode; then
  log "device mode — not launching kiosk"
  exit 0
fi

DISPLAY_MODE="${HOSAKA_DISPLAY_MODE:-}"
if [ -z "$DISPLAY_MODE" ]; then
  preference="${XDG_CONFIG_HOME:-$HOME/.config}/hosaka/display-mode"
  if [ -f "$preference" ]; then
    DISPLAY_MODE="$(cat "$preference")"
  else
    DISPLAY_MODE="gui"
  fi
fi
case "$DISPLAY_MODE" in
  tui)
    for launcher in "$HOME/bin/hosaka-tui-term" "$SCRIPT_DIR/hosaka-tui-term"; do
      if [ -x "$launcher" ]; then
        log "starting canonical TUI (no Electron)"
        exec "$launcher"
      fi
    done
    log "TUI launcher missing"
    exit 1
    ;;
  gui) ;;
  *) log "invalid display mode: $DISPLAY_MODE"; exit 1 ;;
esac

if systemctl is-active --quiet hosaka-kiosk.service 2>/dev/null; then
  log "systemd already owns the kiosk — not starting a second supervisor"
  exit 0
fi

# Brand the desktop substrate before Hosaka appears. If the kiosk is hidden
# later via right-click / desktop mode, the operator lands on a Hosaka app-drawer
# desktop rather than a generic LXQt session.
if [ -x "$BRANDING_SCRIPT" ]; then
  "$BRANDING_SCRIPT" >>"$LOG" 2>&1 || true
fi

if [ ! -x "$ELECTRON_LAUNCHER" ]; then
  log "launcher missing: $ELECTRON_LAUNCHER"
  echo "Hosaka terminal host launcher missing: $ELECTRON_LAUNCHER. Rerun appliance setup." >&2
  exit 1
fi

# Respawn loop: keep Hosaka on top. Bail cleanly if the operator switches to
# device mode at runtime (the next iteration sees it and exits).
while true; do
  while is_device_mode; do sleep 3; done
  if systemctl is-active --quiet hosaka-kiosk.service 2>/dev/null; then
    sleep 3
    continue
  fi
  log "launching electron kiosk"
  if ! "$ELECTRON_LAUNCHER" >>"$LOG" 2>&1; then
    log "terminal host exited unsuccessfully; retrying after backoff"
  fi
  sleep 3
done
