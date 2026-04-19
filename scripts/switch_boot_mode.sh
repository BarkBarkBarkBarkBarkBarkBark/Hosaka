#!/usr/bin/env bash
# Switch Hosaka appliance boot profile without a full reinstall.
#   console  — Python / ANSI shell on tty1 (hosaka-field-terminal)
#   headless — FastAPI + React host on :8421 only (no Chromium)
#   kiosk    — headless + Chromium fullscreen (JavaScript terminal UI on the display)
#
# Usage: ./scripts/switch_boot_mode.sh kiosk
set -euo pipefail

MODE="${1:-}"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SERVICE_CONSOLE="hosaka-field-terminal.service"
SERVICE_HEADLESS="hosaka-field-terminal-headless.service"
SERVICE_WEBSERVER="hosaka-webserver.service"
SERVICE_KIOSK="hosaka-kiosk.service"
PICOCLAW="picoclaw-gateway.service"

if [[ ! "$MODE" =~ ^(console|headless|kiosk)$ ]]; then
  echo "Usage: $0 console|headless|kiosk" >&2
  echo "  console  — tty1 Python shell (not the JS terminal)" >&2
  echo "  headless — web UI at http://<pi>:8421 (build hosaka/web/ui first)" >&2
  echo "  kiosk    — same + Chromium kiosk (needs desktop, chromium, built UI)" >&2
  exit 1
fi

sudo systemctl stop "$SERVICE_CONSOLE" "$SERVICE_HEADLESS" "$SERVICE_WEBSERVER" "$SERVICE_KIOSK" 2>/dev/null || true

for unit in "$SERVICE_CONSOLE" "$SERVICE_HEADLESS" "$SERVICE_WEBSERVER" "$SERVICE_KIOSK" "$PICOCLAW"; do
  if [[ -f "$REPO_ROOT/systemd/$unit" ]]; then
    sudo cp "$REPO_ROOT/systemd/$unit" "/etc/systemd/system/$unit"
  fi
done

sudo install -m 755 "$REPO_ROOT/scripts/kiosk-chromium.sh" /usr/local/bin/hosaka-kiosk-chromium

CURRENT_USER="$(id -un)"
sudo sed -i "s/^User=operator/User=${CURRENT_USER}/" "/etc/systemd/system/$PICOCLAW" 2>/dev/null || true
if [[ -f "/etc/systemd/system/$SERVICE_KIOSK" ]]; then
  sudo sed -i "s/^User=.*/User=${CURRENT_USER}/" "/etc/systemd/system/$SERVICE_KIOSK"
  sudo sed -i "s|^Environment=XAUTHORITY=.*|Environment=XAUTHORITY=/home/${CURRENT_USER}/.Xauthority|" \
    "/etc/systemd/system/$SERVICE_KIOSK"
fi

sudo systemctl daemon-reload
sudo systemctl enable "$PICOCLAW"

for unit in "$SERVICE_CONSOLE" "$SERVICE_HEADLESS" "$SERVICE_WEBSERVER" "$SERVICE_KIOSK"; do
  sudo systemctl disable "$unit" 2>/dev/null || true
done

case "$MODE" in
  console)
    sudo systemctl enable "$SERVICE_CONSOLE"
    sudo systemctl start "$PICOCLAW" "$SERVICE_CONSOLE"
    ;;
  headless)
    sudo systemctl enable "$SERVICE_WEBSERVER"
    sudo systemctl start "$PICOCLAW" "$SERVICE_WEBSERVER"
    ;;
  kiosk)
    sudo systemctl enable "$SERVICE_WEBSERVER" "$SERVICE_KIOSK"
    sudo systemctl start "$PICOCLAW" "$SERVICE_WEBSERVER" "$SERVICE_KIOSK"
    ;;
esac

UI_MARK="$REPO_ROOT/hosaka/web/ui"
if [[ ! -d "$UI_MARK" ]] || ! find "$UI_MARK" -mindepth 1 -maxdepth 1 2>/dev/null | grep -q .; then
  echo "" >&2
  echo "[switch_boot_mode] WARNING: $UI_MARK is empty — the JS shell is not deployed." >&2
  echo "  Run: cd frontend && npm run build  (output: hosaka/web/ui/). See install_hosaka.sh." >&2
fi

if [[ "$MODE" == "kiosk" ]] && ! command -v chromium-browser >/dev/null && ! command -v chromium >/dev/null; then
  echo "" >&2
  echo "[switch_boot_mode] WARNING: no chromium binary — install chromium or chromium-browser." >&2
fi

echo ""
echo "Boot mode is now: $MODE"
echo "Web: http://$(hostname -I | awk '{print $1}'):8421"
