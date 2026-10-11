#!/usr/bin/env bash
set -euo pipefail

SCRIPT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONSOLE_SERVICE="hosaka-field-terminal.service"
HEADLESS_SERVICE="hosaka-field-terminal-headless.service"
WEBSERVER_SERVICE="hosaka-webserver.service"
KIOSK_SERVICE="hosaka-kiosk.service"

find_repo_root() {
  if [[ -n "${HOSAKA_REPO_ROOT:-}" && -d "${HOSAKA_REPO_ROOT}/.git" ]]; then
    echo "${HOSAKA_REPO_ROOT}"
    return
  fi

  if [[ -f /etc/hosaka/repo_root ]]; then
    local recorded
    recorded="$(cat /etc/hosaka/repo_root 2>/dev/null || true)"
    if [[ -n "$recorded" && -d "$recorded/.git" ]]; then
      echo "$recorded"
      return
    fi
  fi

  local candidates=(
    "$SCRIPT_ROOT"
    "$PWD"
    "$HOME/Hosaka"
    "/workspace/cyber_deck"
    "$HOME/cyber_deck"
  )

  local home_candidate
  for home_candidate in /home/*/Hosaka; do
    candidates+=("$home_candidate")
  done
  for home_candidate in /home/*/cyber_deck; do
    candidates+=("$home_candidate")
  done

  local candidate
  for candidate in "${candidates[@]}"; do
    if [[ -d "$candidate/.git" ]]; then
      echo "$candidate"
      return
    fi
  done
}

REPO_ROOT="$(find_repo_root || true)"
if [[ -z "$REPO_ROOT" ]]; then
  echo "[hosaka-update] Could not find git repository root."
  echo "[hosaka-update] Checked /etc/hosaka/repo_root, /opt, cwd, ~/Hosaka, /home/*/Hosaka, and legacy cyber_deck paths."
  echo "[hosaka-update] Set HOSAKA_REPO_ROOT=/path/to/Hosaka and retry."
  exit 1
fi

TARGET_BRANCH="${1:-$(git -C "$REPO_ROOT" rev-parse --abbrev-ref HEAD)}"

cd "$REPO_ROOT"
echo "[hosaka-update] Source checkout: $REPO_ROOT"

echo "[hosaka-update] Fetching remote updates..."
git fetch --all --prune

echo "[hosaka-update] Checking out branch: $TARGET_BRANCH"
git checkout "$TARGET_BRANCH"

echo "[hosaka-update] Pulling latest changes..."
git pull --ff-only

echo "[hosaka-update] Reinstalling Hosaka runtime to /opt..."
"$REPO_ROOT/scripts/install_hosaka.sh"

ACTIVE_SERVICE=""
# Kiosk mode is the appliance default — webserver hosts the API while
# hosaka-kiosk drives Chromium. Check it first so a kiosk Pi actually
# restarts after `update_hosaka.sh`.
if systemctl is-enabled --quiet "$WEBSERVER_SERVICE"; then
  ACTIVE_SERVICE="$WEBSERVER_SERVICE"
elif systemctl is-enabled --quiet "$CONSOLE_SERVICE"; then
  ACTIVE_SERVICE="$CONSOLE_SERVICE"
elif systemctl is-enabled --quiet "$HEADLESS_SERVICE"; then
  ACTIVE_SERVICE="$HEADLESS_SERVICE"
fi

if [[ -n "$ACTIVE_SERVICE" ]]; then
  echo "[hosaka-update] Restarting active service: $ACTIVE_SERVICE"
  sudo systemctl daemon-reload
  sudo systemctl restart "$ACTIVE_SERVICE"
  # Bounce the kiosk too only if someone is deliberately running the
  # systemd unit. The normal appliance path is openbox/autostart inside
  # tty1's X session; starting hosaka-kiosk.service from here has no
  # DISPLAY and crashes in a cache-evicting loop.
  if [[ "$ACTIVE_SERVICE" == "$WEBSERVER_SERVICE" ]] \
      && systemctl is-active --quiet "$KIOSK_SERVICE"; then
    echo "[hosaka-update] Restarting kiosk: $KIOSK_SERVICE"
    sudo systemctl restart "$KIOSK_SERVICE" || true
  fi
  sudo systemctl --no-pager status "$ACTIVE_SERVICE" || true
else
  echo "[hosaka-update] No Hosaka service currently enabled."
  echo "[hosaka-update] Start manually: sudo systemctl start $WEBSERVER_SERVICE"
fi

echo "[hosaka-update] Done."
