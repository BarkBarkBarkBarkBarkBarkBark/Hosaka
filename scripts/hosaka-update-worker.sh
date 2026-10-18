#!/usr/bin/env bash
# Root-owned systemd job; git/npm still run as the operator.
set -euo pipefail

[[ "$(id -u)" == "0" ]] || { echo "The update worker must run under systemd as root." >&2; exit 1; }
REPO_ROOT="${HOSAKA_REPO:?HOSAKA_REPO is required}"
STATE_DIR="${HOSAKA_STATE_DIR:-/var/lib/hosaka}"
OPERATOR="${HOSAKA_OPERATOR:?HOSAKA_OPERATOR is required}"
HOME_DIR="$(getent passwd "$OPERATOR" | cut -d: -f6)"
[[ "$HOME_DIR" == /* ]] || { echo "Cannot find operator home for $OPERATOR." >&2; exit 1; }
DISPLAY_PREFERENCE="${XDG_CONFIG_HOME:-$HOME_DIR/.config}/hosaka/display-mode"
display_mode=gui
if [[ -f "$DISPLAY_PREFERENCE" ]]; then
  display_mode="$(cat "$DISPLAY_PREFERENCE")"
fi
[[ "$display_mode" =~ ^(tui|gui)$ ]] || { echo "Invalid saved display mode at $DISPLAY_PREFERENCE." >&2; exit 1; }
exec 9>/run/lock/hosaka-update.lock
flock -n 9 || { echo "Another Hosaka update is already running." >&2; exit 1; }
export HOSAKA_UPDATE_WORKER=1

previous_mode=console
if [[ -f "$STATE_DIR/mode" ]]; then
  previous_mode="$(cat "$STATE_DIR/mode")"
elif [[ -f /boot/firmware/hosaka-build-mode ]]; then
  previous_mode=device
fi
case "$previous_mode" in
  console|kiosk|device|build) ;;
  *) echo "Invalid existing Hosaka mode: $previous_mode" >&2; exit 1 ;;
esac
services=()
ui_paused=0

restore() {
  local result=$?
  trap - EXIT
  set +e
  local restore_failed=0
  printf '%s\n' "$previous_mode" >"$STATE_DIR/mode" || restore_failed=1
  for unit in "${services[@]}"; do
    if [[ "$unit" == "hosaka-kiosk.service" ]] \
      && [[ "$display_mode" != "gui" || "$previous_mode" == "device" || "$previous_mode" == "build" ]]; then
      continue
    fi
    systemctl start "$unit" || restore_failed=1
  done
  if (( ui_paused )) && [[ "$previous_mode" == "console" || "$previous_mode" == "kiosk" ]]; then
    # Existing graphical supervisors wait through the update. Only start a
    # service when no supervisor owns the window; never reset the login/TTY.
    if [[ "$display_mode" == "gui" ]] && pgrep -x Xorg >/dev/null \
      && ! systemctl is-active --quiet hosaka-kiosk.service \
      && ! pgrep -u "$OPERATOR" -f 'hosaka-lxqt-kiosk|/\.config/openbox/autostart' >/dev/null; then
      systemctl start hosaka-kiosk.service || restore_failed=1
    fi
  fi
  if (( result != 0 || restore_failed )); then
    echo "UPDATE FAILED (exit $result, restore errors $restore_failed). See hosaka update status."
    exit 1
  fi
  local ready=0
  for _ in $(seq 1 30); do
    if curl --noproxy '*' -fsS --max-time 2 http://127.0.0.1:8421/api/health \
      | node -e 'let data=""; process.stdin.on("data", chunk => data += chunk); process.stdin.on("end", () => { try { if (JSON.parse(data).ui_built !== true) process.exit(1); } catch { process.exit(1); } });'; then
      ready=1
      break
    fi
    sleep 1
  done
  if (( ! ready )); then
    echo "UPDATE FAILED: deployed backend/terminal UI did not become healthy." >&2
    exit 1
  fi
  local sha
  if ! sha="$(runuser -u "$OPERATOR" -- git -C "$REPO_ROOT" rev-parse --short=10 HEAD)"; then
    echo "UPDATE FAILED: could not identify the deployed commit." >&2
    exit 1
  fi
  if ! curl --noproxy '*' -fsS --max-time 5 http://127.0.0.1:8421/build-stamp.json \
    | node -e 'let data=""; process.stdin.on("data", chunk => data += chunk); process.stdin.on("end", () => { try { if (JSON.parse(data).sha !== process.argv[1]) process.exit(1); } catch { process.exit(1); } });' "$sha"; then
    echo "UPDATE FAILED: the web server is not serving this commit's frontend build." >&2
    exit 1
  fi
  if [[ "$display_mode" == "gui" && ( "$previous_mode" == "console" || "$previous_mode" == "kiosk" ) ]] \
    && pgrep -x Xorg >/dev/null; then
    local host_ready=0
    for _ in $(seq 1 30); do
      if pgrep -u "$OPERATOR" -f 'kiosk/node_modules/electron/dist/electron' >/dev/null; then
        host_ready=1
        break
      fi
      sleep 1
    done
    if (( ! host_ready )); then
      echo "UPDATE FAILED: terminal + Menu host did not restart; inspect hosaka-kiosk and session logs." >&2
      exit 1
    fi
  fi
  echo "UPDATE COMPLETE: $sha. Saved display ($display_mode) and boot mode ($previous_mode) preserved."
}
trap restore EXIT

echo "Pausing the kiosk and heavy services to free RAM (SSH and the desktop stay up)."
install -d -m 0755 -o "$OPERATOR" "$STATE_DIR"
printf '%s\n' device >"$STATE_DIR/mode"
chown "$OPERATOR" "$STATE_DIR/mode"
ui_paused=1
for unit in hosaka-webserver.service picoclaw-gateway.service hosaka-voice.service hosaka-kiosk.service; do
  if systemctl is-active --quiet "$unit"; then
    services+=("$unit")
    systemctl stop "$unit"
  fi
done
if [[ " ${services[*]} " != *" hosaka-webserver.service "* ]]; then
  services=(hosaka-webserver.service "${services[@]}")
fi
while read -r pid; do
  [[ -n "$pid" ]] && kill "$pid"
done < <(pgrep -u "$OPERATOR" -f 'kiosk/node_modules/electron/dist/electron' || true)

echo "Pulling, building, and deploying the requested checkout."
bash "$REPO_ROOT/scripts/hosaka" update --foreground "$@"
