#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TARGET_BRANCH="${1:-$(git -C "$REPO_ROOT" rev-parse --abbrev-ref HEAD)}"
CONSOLE_SERVICE="hosaka-field-terminal.service"
HEADLESS_SERVICE="hosaka-field-terminal-headless.service"

cd "$REPO_ROOT"

echo "[hosaka-update] Fetching remote updates..."
git fetch --all --prune

echo "[hosaka-update] Checking out branch: $TARGET_BRANCH"
git checkout "$TARGET_BRANCH"

echo "[hosaka-update] Pulling latest changes..."
git pull --ff-only

echo "[hosaka-update] Reinstalling Hosaka runtime to /opt..."
"$REPO_ROOT/scripts/install_hosaka.sh"

ACTIVE_SERVICE=""
if systemctl is-enabled --quiet "$CONSOLE_SERVICE"; then
  ACTIVE_SERVICE="$CONSOLE_SERVICE"
elif systemctl is-enabled --quiet "$HEADLESS_SERVICE"; then
  ACTIVE_SERVICE="$HEADLESS_SERVICE"
fi

if [[ -n "$ACTIVE_SERVICE" ]]; then
  echo "[hosaka-update] Restarting active service: $ACTIVE_SERVICE"
  sudo systemctl daemon-reload
  sudo systemctl restart "$ACTIVE_SERVICE"
  sudo systemctl --no-pager status "$ACTIVE_SERVICE" || true
else
  echo "[hosaka-update] No Hosaka service currently enabled."
  echo "[hosaka-update] Start manually: sudo systemctl start $CONSOLE_SERVICE"
fi

echo "[hosaka-update] Done."
