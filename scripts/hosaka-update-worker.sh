#!/usr/bin/env bash
# Root-owned systemd job; git/npm still run as the operator.
set -euo pipefail

[[ "$(id -u)" == "0" ]] || { echo "The update worker must run under systemd as root." >&2; exit 1; }
REPO_ROOT="${HOSAKA_REPO:?HOSAKA_REPO is required}"
STATE_DIR="${HOSAKA_STATE_DIR:-/var/lib/hosaka}"
OPERATOR="${HOSAKA_OPERATOR:?HOSAKA_OPERATOR is required}"
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
  for unit in "${services[@]}"; do
    systemctl start "$unit" || restore_failed=1
  done
  printf '%s\n' "$previous_mode" >"$STATE_DIR/mode" || restore_failed=1
  if (( ui_paused )) && [[ "$previous_mode" == "console" || "$previous_mode" == "kiosk" ]]; then
    systemctl restart getty@tty1.service || restore_failed=1
  fi
  if (( result != 0 || restore_failed )); then
    echo "UPDATE FAILED (exit $result, restore errors $restore_failed). See hosaka update status."
    exit 1
  fi
  local ready=0
  for _ in $(seq 1 30); do
    if curl --noproxy '*' -fsS --max-time 2 http://127.0.0.1:8421/api/health >/dev/null; then ready=1; break; fi
    sleep 1
  done
  if (( ! ready )); then
    echo "UPDATE FAILED: deployed web server did not become healthy." >&2
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
  echo "UPDATE COMPLETE: $sha. Boot display is the saved terminal GUI preference."
}
trap restore EXIT

echo "Pausing the kiosk and heavy services to free RAM (SSH and the desktop stay up)."
install -d -m 0755 -o "$OPERATOR" "$STATE_DIR"
printf '%s\n' device >"$STATE_DIR/mode"
chown "$OPERATOR" "$STATE_DIR/mode"
ui_paused=1
for unit in hosaka-webserver.service picoclaw-gateway.service hosaka-voice.service hosaka-kiosk.service; do
  if systemctl is-active --quiet "$unit"; then
    # The graphical autostart owns kiosk restoration, not a second supervisor.
    [[ "$unit" == "hosaka-kiosk.service" ]] || services+=("$unit")
    systemctl stop "$unit"
  fi
done
if [[ " ${services[*]} " != *" hosaka-webserver.service "* ]]; then
  services=(hosaka-webserver.service "${services[@]}")
fi
while read -r pid; do
  [[ -n "$pid" ]] && kill "$pid"
done < <(pgrep -u "$OPERATOR" -f 'hosaka-lxqt-kiosk|/\.config/openbox/autostart|kiosk/node_modules/electron/dist/electron' || true)

echo "Pulling, building, and deploying the requested checkout."
bash "$REPO_ROOT/scripts/hosaka" update --foreground "$@"
