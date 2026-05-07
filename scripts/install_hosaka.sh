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
sudo mkdir -p /etc/hosaka
printf '%s\n' "$REPO_ROOT" | sudo tee /etc/hosaka/repo_root >/dev/null
sudo rsync -a --delete "$REPO_ROOT/hosaka"               "$APP_ROOT/"
sudo rsync -a --delete "$REPO_ROOT/docs"                 "$APP_ROOT/"
sudo rsync -a --delete "$REPO_ROOT/scripts"              "$APP_ROOT/"
# Flatpak app manifests (consumed by hosaka.web.api_v1 _read_app_manifests).
# Exclude macOS AppleDouble sidecars (._*) so the YAML loader stays clean.
if [[ -d "$REPO_ROOT/hosaka-apps" ]]; then
  sudo rsync -a --delete --exclude='._*' --exclude='.DS_Store' \
    "$REPO_ROOT/hosaka-apps" "$APP_ROOT/"
fi
sudo rsync -a           "$REPO_ROOT/README.md"           "$APP_ROOT/"
sudo rsync -a           "$REPO_ROOT/requirements-hosaka.txt" "$APP_ROOT/"

sudo install -m 755 "$REPO_ROOT/scripts/kiosk-chromium.sh"   /usr/local/bin/hosaka-kiosk-chromium
sudo install -m 755 "$REPO_ROOT/scripts/kiosk-electron.sh"   /usr/local/bin/hosaka-kiosk-electron
# Operator CLI (build/kiosk mode toggle, deploy, status) and the boot-mode
# arbiter that the hosaka-mode.service runs at startup. Both are optional —
# older repo snapshots may not ship them yet, so don't fail the install.
if [[ -f "$REPO_ROOT/scripts/hosaka" ]]; then
  sudo install -m 755 "$REPO_ROOT/scripts/hosaka"            /usr/local/bin/hosaka
fi
if [[ -f "$REPO_ROOT/scripts/hosaka-mode-init" ]]; then
  sudo install -m 755 "$REPO_ROOT/scripts/hosaka-mode-init"  /usr/local/bin/hosaka-mode-init
fi

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
  chromium_ok=0
  for pkg in chromium chromium-browser; do
    if sudo apt-get install -y "$pkg"; then
      ok "Installed apt package: $pkg"
      chromium_ok=1
      break
    fi
  done
  if [[ "$chromium_ok" -eq 0 ]]; then
    echo "[install] WARNING: neither chromium nor chromium-browser installed — try: sudo apt-cache search chromium" >&2
  fi
  sudo apt-get install -y unclutter xdotool
  ok "Kiosk utilities (unclutter, xdotool) installed."
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
  sudo rsync -a --delete "$REPO_ROOT/hosaka/web/ui/" "$UI_DEST/"
  ok "Frontend built and deployed to $UI_DEST"
  cd - >/dev/null
else
  echo "Warning: frontend source not found at $FRONTEND_SRC — skipping SPA build." >&2
  echo "Clone hosaka_field-terminal/frontend alongside this repo, or build manually." >&2
fi

# ── Electron kiosk deps (only installed when kiosk mode is the target) ───────
KIOSK_SRC="$REPO_ROOT/kiosk"
if [[ "$HOSAKA_BOOT_MODE" == "kiosk" && -d "$KIOSK_SRC" ]]; then
  info "Installing Electron kiosk dependencies..."
  cd "$KIOSK_SRC"
  # --omit=dev skips nothing meaningful here (electron itself is a devDep
  # that we still need at runtime) — we install everything.
  npm install --no-fund --no-audit --loglevel error
  sudo mkdir -p "$APP_ROOT/kiosk"
  sudo rsync -a --delete "$KIOSK_SRC/" "$APP_ROOT/kiosk/"
  ok "Electron kiosk staged at $APP_ROOT/kiosk"
  cd - >/dev/null
fi

# ── state directories ─────────────────────────────────────────────────────────
sudo install -d -m 755 /var/lib/hosaka
mkdir -p "$HOME/.hosaka"

# ── systemd units ─────────────────────────────────────────────────────────────
info "Installing systemd units..."
PICOCLAW_SERVICE_NAME="picoclaw-gateway.service"
HOSAKA_MODE_SERVICE="hosaka-mode.service"
for unit in "$SERVICE_CONSOLE" "$SERVICE_HEADLESS" "$SERVICE_WEBSERVER" "$SERVICE_KIOSK" "$PICOCLAW_SERVICE_NAME" "$HOSAKA_MODE_SERVICE"; do
  if [[ -f "$REPO_ROOT/systemd/$unit" ]]; then
    sudo cp "$REPO_ROOT/systemd/$unit" "/etc/systemd/system/$unit"
  fi
done

# Mask noisy units that don't apply on this headless Pi (no sound card → ALSA
# spam in the journal every boot, slow boot from waiting on dnf-makecache-style
# refreshes, etc.). Best-effort; ignore failures on hosts where they're absent.
for unit in alsa-restore.service alsa-state.service; do
  sudo systemctl mask "$unit" 2>/dev/null || true
done

# Patch picoclaw service user to match whoever is running the install
CURRENT_USER="$(id -un)"
CURRENT_HOME="$(getent passwd "$CURRENT_USER" | cut -d: -f6)"
sudo sed -i "s/^User=operator/User=${CURRENT_USER}/" "/etc/systemd/system/$PICOCLAW_SERVICE_NAME" 2>/dev/null || true

# Openbox owns the actual X11 kiosk session on the appliance. Keep the
# checked-in autostart in sync so fixes to kiosk supervision / portal env
# imports take effect after updates.
if [[ -n "$CURRENT_HOME" && -f "$REPO_ROOT/dotfiles/openbox/autostart" ]]; then
  sudo install -D -m 755 -o "$CURRENT_USER" -g "$CURRENT_USER" \
    "$REPO_ROOT/dotfiles/openbox/autostart" "$CURRENT_HOME/.config/openbox/autostart"
fi

# Kiosk Chromium must run as the graphical-session user (X11 cookie path).
if [[ -f "/etc/systemd/system/$SERVICE_KIOSK" ]]; then
  sudo sed -i "s/^User=.*/User=${CURRENT_USER}/" "/etc/systemd/system/$SERVICE_KIOSK"
  sudo sed -i "s|^Environment=XAUTHORITY=.*|Environment=XAUTHORITY=/home/${CURRENT_USER}/.Xauthority|" \
    "/etc/systemd/system/$SERVICE_KIOSK"
fi

sudo systemctl daemon-reload

# Always enable picoclaw gateway and the boot-mode arbiter
sudo systemctl enable "$PICOCLAW_SERVICE_NAME"
sudo systemctl enable "$HOSAKA_MODE_SERVICE" 2>/dev/null || true

# ── disable all hosaka modes, then enable the right one ───────────────────────
for unit in "$SERVICE_CONSOLE" "$SERVICE_HEADLESS" "$SERVICE_WEBSERVER" "$SERVICE_KIOSK"; do
  sudo systemctl disable "$unit" 2>/dev/null || true
done

case "$HOSAKA_BOOT_MODE" in
  kiosk)
    sudo systemctl enable "$SERVICE_WEBSERVER"
    # Do NOT enable hosaka-kiosk.service here. The appliance starts X via
    # tty1 autologin -> startx -> openbox, and openbox/autostart supervises
    # Electron inside that real X session. A systemd-launched kiosk has no
    # DISPLAY/XAUTHORITY, crashes in a loop, evicts the live Chromium cache,
    # and makes the wall flash. Keep the unit installed for manual debugging,
    # but disabled by default.
    sudo systemctl disable "$SERVICE_KIOSK" 2>/dev/null || true
    ok "Kiosk mode enabled: webserver on boot; openbox supervises Electron on tty1."
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
