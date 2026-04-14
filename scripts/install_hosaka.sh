#!/usr/bin/env bash
set -euo pipefail

APP_ROOT="/opt/hosaka-field-terminal"
SERVICE_NAME="hosaka-field-terminal.service"
HEADLESS_SERVICE_NAME="hosaka-field-terminal-headless.service"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"
INSTALL_TAILSCALE="${INSTALL_TAILSCALE:-0}"
INSTALL_CADDY="${INSTALL_CADDY:-0}"

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  echo "python3 is required" >&2
  exit 1
fi

sudo mkdir -p "$APP_ROOT"
sudo rsync -a --delete "$REPO_ROOT/hosaka" "$APP_ROOT/"
sudo rsync -a --delete "$REPO_ROOT/docs" "$APP_ROOT/"
sudo rsync -a --delete "$REPO_ROOT/scripts" "$APP_ROOT/"
sudo rsync -a "$REPO_ROOT/README.md" "$APP_ROOT/"
sudo rsync -a "$REPO_ROOT/requirements-hosaka.txt" "$APP_ROOT/"

if [[ "$INSTALL_TAILSCALE" == "1" ]]; then
  if ! command -v tailscale >/dev/null 2>&1; then
    curl -fsSL https://tailscale.com/install.sh | sh
  fi
fi

if [[ "$INSTALL_CADDY" == "1" ]]; then
  if ! command -v caddy >/dev/null 2>&1; then
    sudo apt-get update
    sudo apt-get install -y debian-keyring debian-archive-keyring apt-transport-https curl
    curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | sudo gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
    curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | sudo tee /etc/apt/sources.list.d/caddy-stable.list
    sudo apt-get update
    sudo apt-get install -y caddy
  fi
fi

sudo "$PYTHON_BIN" -m venv "$APP_ROOT/.venv"
sudo "$APP_ROOT/.venv/bin/pip" install --upgrade pip
sudo "$APP_ROOT/.venv/bin/pip" install -r "$APP_ROOT/requirements-hosaka.txt"

sudo install -d -m 755 /var/lib/hosaka
sudo cp "$REPO_ROOT/systemd/$SERVICE_NAME" "/etc/systemd/system/$SERVICE_NAME"
sudo cp "$REPO_ROOT/systemd/$HEADLESS_SERVICE_NAME" "/etc/systemd/system/$HEADLESS_SERVICE_NAME"
sudo systemctl daemon-reload
sudo systemctl enable "$SERVICE_NAME"
sudo systemctl disable "$HEADLESS_SERVICE_NAME" >/dev/null 2>&1 || true

echo "Hosaka Field Terminal installed."
echo "Start now: sudo systemctl start $SERVICE_NAME"
