#!/usr/bin/env bash
set -euo pipefail

APP_ROOT="/opt/hosaka-field-terminal"
SERVICE_CONSOLE="hosaka-field-terminal.service"
SERVICE_HEADLESS="hosaka-field-terminal-headless.service"
SERVICE_WEBSERVER="hosaka-webserver.service"
SERVICE_KIOSK="hosaka-kiosk.service"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"
INSTALL_TAILSCALE="${INSTALL_TAILSCALE:-1}"    # default ON for appliance
INSTALL_CADDY="${INSTALL_CADDY:-0}"
INSTALL_DOCKER="${INSTALL_DOCKER:-0}"
HOSAKA_BOOT_MODE="${HOSAKA_BOOT_MODE:-kiosk}"  # kiosk | console | headless

GREEN='\033[0;32m'; CYAN='\033[0;36m'; NC='\033[0m'
info() { echo -e "${CYAN}[install]${NC} $*"; }
ok()   { echo -e "${GREEN}[install]${NC} $*"; }

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  echo "python3 is required" >&2
  exit 1
fi

# ── sync repo files ───────────────────────────────────────────────────────────
sudo mkdir -p "$APP_ROOT"
sudo rsync -a --delete "$REPO_ROOT/hosaka"               "$APP_ROOT/"
sudo rsync -a --delete "$REPO_ROOT/docs"                 "$APP_ROOT/"
sudo rsync -a --delete "$REPO_ROOT/scripts"              "$APP_ROOT/"
sudo rsync -a           "$REPO_ROOT/README.md"           "$APP_ROOT/"
sudo rsync -a           "$REPO_ROOT/requirements-hosaka.txt" "$APP_ROOT/"

# ── Tailscale ────────────────────────────────────────────────────────────────
if [[ "$INSTALL_TAILSCALE" == "1" ]]; then
  if ! command -v tailscale >/dev/null 2>&1; then
    info "Installing Tailscale..."
    curl -fsSL https://tailscale.com/install.sh | sh
    ok "Tailscale installed. Run: sudo tailscale up"
  else
    ok "Tailscale already installed."
  fi
fi

# ── Caddy (optional reverse proxy) ───────────────────────────────────────────
if [[ "$INSTALL_CADDY" == "1" ]]; then
  if ! command -v caddy >/dev/null 2>&1; then
    info "Installing Caddy..."
    sudo apt-get update -qq
    sudo apt-get install -y debian-keyring debian-archive-keyring apt-transport-https curl
    curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' \
      | sudo gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
    curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' \
      | sudo tee /etc/apt/sources.list.d/caddy-stable.list
    sudo apt-get update -qq
    sudo apt-get install -y caddy
  fi
fi

# ── Node.js 20 (LTS) — needed to build the frontend SPA ─────────────────────
if ! command -v node >/dev/null 2>&1 || [[ "$(node -e 'process.stdout.write(process.version.split(".")[0].replace("v",""))')" -lt 20 ]]; then
  info "Installing Node.js 20 LTS..."
  curl -fsSL https://deb.nodesource.com/setup_20.x | sudo bash -
  sudo apt-get install -y nodejs
  ok "Node.js $(node --version) installed."
else
  ok "Node.js $(node --version) already installed."
fi

# ── Chromium + kiosk utilities ────────────────────────────────────────────────
if [[ "$HOSAKA_BOOT_MODE" == "kiosk" ]]; then
  info "Installing Chromium and kiosk utilities..."
  sudo apt-get update -qq
  sudo apt-get install -y chromium-browser unclutter xdotool
  ok "Chromium and kiosk utilities installed."
fi

# ── Docker (optional smoke-test image) ───────────────────────────────────────
if [[ "$INSTALL_DOCKER" == "1" ]]; then
  if ! command -v docker >/dev/null 2>&1; then
    info "Installing Docker..."
    curl -fsSL https://get.docker.com | sh
    sudo usermod -aG docker "${SUDO_USER:-pi}"
    ok "Docker installed. Log out and back in for group membership to take effect."
  fi
fi

# ── network tools (arp-scan, nmap for /netscan) ───────────────────────────────
info "Installing network tools..."
sudo apt-get install -y arp-scan nmap 2>/dev/null || true
ok "Network tools ready."

# ── Python venv ───────────────────────────────────────────────────────────────
info "Setting up Python virtualenv..."
sudo "$PYTHON_BIN" -m venv "$APP_ROOT/.venv"
sudo "$APP_ROOT/.venv/bin/pip" install --upgrade pip -q
sudo "$APP_ROOT/.venv/bin/pip" install -r "$APP_ROOT/requirements-hosaka.txt" -q
# uvicorn is needed by hosaka-webserver.service
sudo "$APP_ROOT/.venv/bin/pip" install uvicorn[standard] -q
ok "Python environment ready."

# ── build the frontend SPA ────────────────────────────────────────────────────
FRONTEND_SRC="$REPO_ROOT/frontend"
UI_DEST="$APP_ROOT/hosaka/web/ui"

if [[ -d "$FRONTEND_SRC" ]]; then
  info "Building frontend SPA..."
  cd "$FRONTEND_SRC"
  # Use appliance env — points API calls at local FastAPI server
  if [[ -f ".env.appliance" ]]; then
    cp ".env.appliance" ".env.local"
  fi
  npm ci --prefer-offline --loglevel error
  npm run build
  sudo mkdir -p "$UI_DEST"
  sudo rsync -a --delete dist/ "$UI_DEST/"
  ok "Frontend built and deployed to $UI_DEST"
  cd - >/dev/null
else
  echo "Warning: frontend source not found at $FRONTEND_SRC — skipping SPA build." >&2
  echo "Clone hosaka_field-terminal/frontend alongside this repo, or build manually." >&2
fi

# ── state directory ───────────────────────────────────────────────────────────
sudo install -d -m 755 /var/lib/hosaka

# ── systemd units ────────────────────────────────────────────────────────────
info "Installing systemd units..."
for unit in "$SERVICE_CONSOLE" "$SERVICE_HEADLESS" "$SERVICE_WEBSERVER" "$SERVICE_KIOSK"; do
  if [[ -f "$REPO_ROOT/systemd/$unit" ]]; then
    sudo cp "$REPO_ROOT/systemd/$unit" "/etc/systemd/system/$unit"
  fi
done
sudo systemctl daemon-reload

# ── disable all, then enable the right set ───────────────────────────────────
for unit in "$SERVICE_CONSOLE" "$SERVICE_HEADLESS" "$SERVICE_WEBSERVER" "$SERVICE_KIOSK"; do
  sudo systemctl disable "$unit" 2>/dev/null || true
done

case "$HOSAKA_BOOT_MODE" in
  kiosk)
    sudo systemctl enable "$SERVICE_WEBSERVER"
    sudo systemctl enable "$SERVICE_KIOSK"
    ok "Kiosk mode enabled: webserver + Chromium kiosk on boot."
    ;;
  headless)
    sudo systemctl enable "$SERVICE_WEBSERVER"
    ok "Headless mode enabled: web server only, no kiosk display."
    ;;
  console)
    sudo systemctl enable "$SERVICE_CONSOLE"
    ok "Console mode enabled: Python TUI on tty1."
    ;;
  *)
    echo "Unknown HOSAKA_BOOT_MODE=$HOSAKA_BOOT_MODE" >&2
    ;;
esac

echo ""
ok "Hosaka installation complete."
echo "  Boot mode:  $HOSAKA_BOOT_MODE"
echo "  Web UI:     http://$(hostname -I | awk '{print $1}'):8421"
echo "  Setup:      http://$(hostname -I | awk '{print $1}'):8421/setup"
echo "  Smoke test: $APP_ROOT/scripts/smoke_test.sh"
