#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────────────────
# setup_hosaka.sh — One-shot red-carpet bootstrap for Hosaka Field Terminal
#
# This is the ONLY script a new user needs to run on a fresh Raspberry Pi.
# It chains everything: Hosaka install → service enable → boot.
#
# Requires: picoclaw already installed at /usr/local/bin/picoclaw
#   Install: https://github.com/sipeed/picoclaw/releases
#
# Usage:
#   ./scripts/setup_hosaka.sh
#
# Environment variables (all optional):
#   INSTALL_TAILSCALE 1 to install Tailscale     (default: 1)
#   INSTALL_CADDY     1 to install Caddy         (default: 0)
#   HOSAKA_BOOT_MODE  kiosk | headless | console  (default: kiosk)
#   OPENAI_API_KEY    OpenAI key (written to .env if set)
#   SKIP_SMOKE_TEST   1 to skip post-install tests (default: 0)
# ──────────────────────────────────────────────────────────────────────────────
set -euo pipefail

GREEN='\033[0;32m'
CYAN='\033[0;36m'
YELLOW='\033[1;33m'
NC='\033[0m'

banner() {
  echo ""
  echo -e "${CYAN}╔══════════════════════════════════════════════════╗${NC}"
  echo -e "${CYAN}║                                                  ║${NC}"
  echo -e "${CYAN}║     ${GREEN}HOSAKA FIELD TERMINAL${CYAN}                        ║${NC}"
  echo -e "${CYAN}║     ${NC}Red Carpet Setup${CYAN}                              ║${NC}"
  echo -e "${CYAN}║                                                  ║${NC}"
  echo -e "${CYAN}╚══════════════════════════════════════════════════╝${NC}"
  echo ""
}

info()  { echo -e "${CYAN}[hosaka]${NC} $*"; }
ok()    { echo -e "${GREEN}[hosaka]${NC} $*"; }
warn()  { echo -e "${YELLOW}[hosaka]${NC} $*"; }

# ── locate repo root ─────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

if [[ ! -f "$REPO_ROOT/requirements-hosaka.txt" ]]; then
  echo "Error: Cannot locate Hosaka repo root from $SCRIPT_DIR" >&2
  echo "Make sure you run this from inside the cloned repo." >&2
  exit 1
fi

# ── step 1: check picoclaw ──────────────────────────────────────────────────
banner
info "Step 1/3 — Checking picoclaw..."

if ! command -v picoclaw >/dev/null 2>&1; then
  echo ""
  echo "  picoclaw is not installed. Install it first:"
  echo "  https://github.com/sipeed/picoclaw/releases"
  echo ""
  echo "  Then run 'picoclaw onboard' and rerun this script."
  exit 1
fi

PICOCLAW_VERSION="$(picoclaw version 2>/dev/null | grep -oP 'picoclaw \K[^\s]+' || echo 'unknown')"
ok "picoclaw ${PICOCLAW_VERSION} found at $(command -v picoclaw)"

if [[ ! -f "$HOME/.picoclaw/config.json" ]]; then
  warn "No picoclaw config found. Running 'picoclaw onboard'..."
  picoclaw onboard
fi

info "Generating Hosaka-linked PicoClaw runtime files..."
python "$REPO_ROOT/scripts/bootstrap_picoclaw_runtime.py" --home "$HOME"
ok "PicoClaw runtime now derives identity, manager policy, and Hosaka skills from this repo."

echo ""

# ── step 2: install Hosaka ───────────────────────────────────────────────────
info "Step 2/3 — Installing Hosaka Field Terminal..."
echo ""
HOSAKA_BOOT_MODE="${HOSAKA_BOOT_MODE:-kiosk}" \
  INSTALL_TAILSCALE="${INSTALL_TAILSCALE:-1}" \
  INSTALL_CADDY="${INSTALL_CADDY:-0}" \
  bash "$REPO_ROOT/scripts/install_hosaka.sh"
echo ""
ok "Hosaka installed."

# ── step 3: configure boot mode ──────────────────────────────────────────────
BOOT_MODE="${HOSAKA_BOOT_MODE:-kiosk}"
info "Step 3/4 — Configuring boot mode: ${BOOT_MODE}"

# Disable legacy service names (safe no-op if they don't exist)
for svc in hosaka-field-terminal.service hosaka-field-terminal-headless.service; do
  sudo systemctl disable "$svc" 2>/dev/null || true
  sudo systemctl stop "$svc" 2>/dev/null || true
done

case "$BOOT_MODE" in
  kiosk)
    sudo systemctl enable hosaka-webserver.service hosaka-kiosk.service
    sudo systemctl disable hosaka-console.service 2>/dev/null || true
    ok "Kiosk mode: Chromium on :8421 will auto-start at boot."
    ;;
  headless)
    sudo systemctl enable hosaka-webserver.service
    sudo systemctl disable hosaka-kiosk.service hosaka-console.service 2>/dev/null || true
    ok "Headless mode: web UI at :8421, no Chromium."
    ;;
  console)
    sudo systemctl enable hosaka-console.service
    sudo systemctl disable hosaka-webserver.service hosaka-kiosk.service 2>/dev/null || true
    ok "Console mode: Python TUI on tty1."
    ;;
  *)
    warn "Unknown boot mode '${BOOT_MODE}'. Defaulting to kiosk."
    sudo systemctl enable hosaka-webserver.service hosaka-kiosk.service
    ;;
esac

# ── write OpenAI key to .env if provided ─────────────────────────────────────
ENV_FILE="/opt/hosaka-field-terminal/.env"
if [[ -n "${OPENAI_API_KEY:-}" ]]; then
  if grep -q "^OPENAI_API_KEY=" "$ENV_FILE" 2>/dev/null; then
    sudo sed -i "s|^OPENAI_API_KEY=.*|OPENAI_API_KEY=${OPENAI_API_KEY}|" "$ENV_FILE"
  else
    echo "OPENAI_API_KEY=${OPENAI_API_KEY}" | sudo tee -a "$ENV_FILE" > /dev/null
  fi
  ok "OpenAI API key written to ${ENV_FILE}."
fi

# ── step 4: start services ───────────────────────────────────────────────────
info "Step 4/4 — Starting Hosaka..."

# Always start the picoclaw gateway first
sudo systemctl restart picoclaw-gateway.service
ok "Picoclaw gateway started."

case "$BOOT_MODE" in
  kiosk)
    sudo systemctl restart hosaka-webserver.service
    sleep 2
    sudo systemctl restart hosaka-kiosk.service
    ;;
  headless)
    sudo systemctl restart hosaka-webserver.service
    ;;
  console)
    sudo systemctl restart hosaka-console.service
    ;;
esac

# ── smoke test ───────────────────────────────────────────────────────────────
if [[ "${SKIP_SMOKE_TEST:-0}" != "1" ]]; then
  echo ""
  info "Running smoke tests (SKIP_SMOKE_TEST=1 to skip)..."
  bash "$REPO_ROOT/scripts/smoke_test.sh" || warn "Some smoke tests failed — check output above."
fi

# ── detect IP for the user ───────────────────────────────────────────────────
LOCAL_IP=$(hostname -I 2>/dev/null | awk '{print $1}')
WEB_PORT="${HOSAKA_WEB_PORT:-8421}"

echo ""
echo -e "${CYAN}╔══════════════════════════════════════════════════╗${NC}"
echo -e "${CYAN}║                                                  ║${NC}"
echo -e "${CYAN}║  ${GREEN}✓ Hosaka Field Terminal is live.${CYAN}                ║${NC}"
echo -e "${CYAN}║                                                  ║${NC}"
if [[ -n "$LOCAL_IP" ]]; then
  PAD=$(( 26 - ${#LOCAL_IP} - ${#WEB_PORT} ))
  echo -e "${CYAN}║  ${NC}Web UI:  http://${LOCAL_IP}:${WEB_PORT}${CYAN}$(printf '%*s' $PAD '')║${NC}"
fi
echo -e "${CYAN}║  ${NC}Mode:    ${BOOT_MODE}${CYAN}$(printf '%*s' $(( 39 - ${#BOOT_MODE} )) '')║${NC}"
echo -e "${CYAN}║  ${NC}Reboot to fully activate kiosk autostart.${CYAN}  ║${NC}"
echo -e "${CYAN}║                                                  ║${NC}"
echo -e "${CYAN}║  ${NC}No Wrong Way.${CYAN}                                   ║${NC}"
echo -e "${CYAN}║                                                  ║${NC}"
echo -e "${CYAN}╚══════════════════════════════════════════════════╝${NC}"
echo ""

if [[ "$BOOT_MODE" == "console" ]] && [[ -t 0 ]]; then
  read -rp "Press Enter to start Hosaka console now (or Ctrl-C to do it later)... "
  echo ""
  info "Launching Hosaka console..."
  sudo /opt/hosaka-field-terminal/.venv/bin/python -m hosaka
fi
