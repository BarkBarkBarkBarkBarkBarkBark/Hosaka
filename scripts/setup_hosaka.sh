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
#   INSTALL_TAILSCALE 1 to install Tailscale     (default: 0)
#   INSTALL_CADDY     1 to install Caddy         (default: 0)
#   HOSAKA_BOOT_MODE  console or headless         (default: console)
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

# ── step 1: check picoclaw ───────────────────────────────────────────────────
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

echo ""

# ── step 2: install Hosaka ───────────────────────────────────────────────────
info "Step 2/3 — Installing Hosaka Field Terminal..."
echo ""
bash "$REPO_ROOT/scripts/install_hosaka.sh"
echo ""
ok "Hosaka installed."

# ── step 3: configure boot mode and start ────────────────────────────────────
BOOT_MODE="${HOSAKA_BOOT_MODE:-console}"
info "Step 3/3 — Configuring boot mode: ${BOOT_MODE}"

sudo systemctl start picoclaw-gateway.service
ok "Picoclaw gateway started."

if [[ "$BOOT_MODE" == "headless" ]]; then
  sudo systemctl disable hosaka-field-terminal.service 2>/dev/null || true
  sudo systemctl enable hosaka-field-terminal-headless.service
  sudo systemctl start hosaka-field-terminal-headless.service
  ok "Headless mode enabled."
else
  sudo systemctl disable hosaka-field-terminal-headless.service 2>/dev/null || true
  sudo systemctl enable hosaka-field-terminal.service
  sudo systemctl start hosaka-field-terminal.service
  ok "Console mode enabled. Setup will happen on tty1."
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
echo -e "${CYAN}║  ${NC}Web setup: http://${LOCAL_IP}:${WEB_PORT}${CYAN}$(printf '%*s' $((18 - ${#LOCAL_IP} - ${#WEB_PORT})) '')║${NC}"
fi
echo -e "${CYAN}║  ${NC}Console:   switch to tty1 or reboot${CYAN}             ║${NC}"
echo -e "${CYAN}║  ${NC}Chat:      just type at the hosaka> prompt${CYAN}       ║${NC}"
echo -e "${CYAN}║                                                  ║${NC}"
echo -e "${CYAN}║  ${NC}No Wrong Way.${CYAN}                                   ║${NC}"
echo -e "${CYAN}║                                                  ║${NC}"
echo -e "${CYAN}╚══════════════════════════════════════════════════╝${NC}"
echo ""

if [[ "$BOOT_MODE" != "headless" ]] && [[ -t 0 ]]; then
  echo ""
  read -rp "Press Enter to start onboarding now (or Ctrl-C to do it later)... "
  echo ""
  info "Launching Hosaka console..."
  sudo /opt/hosaka-field-terminal/.venv/bin/python -m hosaka
fi
