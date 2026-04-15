#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────────────────
# install_openclaw.sh — Onboard OpenClaw (and install Node.js if on bare metal)
#
# In Docker: Node.js 24 + openclaw are already baked into the image.
#            This script only runs onboarding (first-time ~/.openclaw/openclaw.json)
#            and model configuration.  Launcher.py also runs this automatically
#            on first boot, so you rarely need to invoke it manually.
#
# Bare metal (Pi/Debian): installs Node.js 24 via nodesource, then openclaw
#            via npm, then runs onboarding.
#
# Usage:
#   ./scripts/install_openclaw.sh
#
# Environment variables:
#   OPENAI_API_KEY          Required — passed to openclaw onboard
#   OPENAI_MODEL            Model to configure  (default: gpt-4o-mini)
#   OPENCLAW_GATEWAY_PORT   Gateway port        (default: 18789)
#   OPENCLAW_GATEWAY_TOKEN  Optional auth token for the gateway
# ──────────────────────────────────────────────────────────────────────────────
set -euo pipefail

OPENAI_KEY="${OPENAI_API_KEY:-}"
OPENAI_MODEL="${OPENAI_MODEL:-gpt-4o-mini}"
GATEWAY_PORT="${OPENCLAW_GATEWAY_PORT:-18789}"
GATEWAY_TOKEN="${OPENCLAW_GATEWAY_TOKEN:-}"

# ── colors ────────────────────────────────────────────────────────────────────
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
CYAN='\033[0;36m'
NC='\033[0m'

info() { echo -e "${CYAN}[openclaw]${NC} $*"; }
ok()   { echo -e "${GREEN}[openclaw]${NC} $*"; }
warn() { echo -e "${YELLOW}[openclaw]${NC} $*"; }
fail() { echo -e "${RED}[openclaw]${NC} $*" >&2; }

# ── guards ────────────────────────────────────────────────────────────────────
if [[ -z "$OPENAI_KEY" ]]; then
  fail "OPENAI_API_KEY is not set.  Export it before running this script:"
  fail "  export OPENAI_API_KEY=sk-..."
  exit 1
fi

# ── detect OS ─────────────────────────────────────────────────────────────────
OS="$(uname -s)"

# ── Step 1: Ensure Node.js 24 is installed ────────────────────────────────────
install_node() {
  if command -v node >/dev/null 2>&1; then
    NODE_MAJOR="$(node --version | sed 's/v\([0-9]*\).*/\1/')"
    if [[ "$NODE_MAJOR" -ge 18 ]]; then
      ok "Node.js $(node --version) already installed."
      return 0
    fi
    warn "Node.js $(node --version) found but Node 18+ required. Upgrading..."
  fi

  info "Installing Node.js 24..."

  if [[ "$OS" == "Linux" ]]; then
    if command -v apt-get >/dev/null 2>&1; then
      curl -fsSL https://deb.nodesource.com/setup_24.x | bash -
      apt-get install -y nodejs
    elif command -v dnf >/dev/null 2>&1; then
      curl -fsSL https://rpm.nodesource.com/setup_24.x | bash -
      dnf install -y nodejs
    elif command -v yum >/dev/null 2>&1; then
      curl -fsSL https://rpm.nodesource.com/setup_24.x | bash -
      yum install -y nodejs
    else
      fail "Unsupported Linux package manager. Install Node.js 18+ manually."
      exit 1
    fi
  elif [[ "$OS" == "Darwin" ]]; then
    if command -v brew >/dev/null 2>&1; then
      brew install node@24 || brew upgrade node
    else
      fail "Homebrew not found.  Install Node.js from https://nodejs.org"
      exit 1
    fi
  else
    fail "Unsupported OS: $OS.  Install Node.js 18+ manually from https://nodejs.org"
    exit 1
  fi

  if ! command -v node >/dev/null 2>&1; then
    fail "Node.js installation failed — 'node' binary not on PATH."
    exit 1
  fi
  ok "Node.js $(node --version) installed."
}

# ── Step 2: Install openclaw CLI via npm ──────────────────────────────────────
install_openclaw_cli() {
  if command -v openclaw >/dev/null 2>&1; then
    CURRENT_VERSION="$(openclaw --version 2>/dev/null | head -1 || echo 'unknown')"
    ok "openclaw already installed: $CURRENT_VERSION"
    info "Checking for updates..."
    npm install -g openclaw@latest 2>&1 | tail -1 || true
  else
    info "Installing openclaw CLI..."
    npm install -g openclaw@latest
  fi

  if ! command -v openclaw >/dev/null 2>&1; then
    fail "openclaw installation failed — 'openclaw' binary not on PATH."
    exit 1
  fi
  ok "openclaw $(openclaw --version 2>/dev/null | head -1 || echo '') installed."
}

# ── Step 3: Onboard (first-time config) ──────────────────────────────────────
onboard_openclaw() {
  CONFIG_FILE="$HOME/.openclaw/openclaw.json"

  if [[ -f "$CONFIG_FILE" ]]; then
    ok "OpenClaw config already exists at $CONFIG_FILE — skipping onboard."
    info "To re-onboard, delete the config and rerun this script."
    return 0
  fi

  info "Running non-interactive onboard with OpenAI backend..."

  ONBOARD_ARGS=(
    onboard
    --non-interactive
    --auth-choice openai-api-key
    --openai-api-key "$OPENAI_KEY"
    --skip-skills
    --skip-health
    --accept-risk
  )

  if [[ "$GATEWAY_PORT" != "18789" ]]; then
    ONBOARD_ARGS+=(--gateway-port "$GATEWAY_PORT")
  fi

  if [[ -n "$GATEWAY_TOKEN" ]]; then
    ONBOARD_ARGS+=(--gateway-auth token --gateway-token "$GATEWAY_TOKEN")
  fi

  openclaw "${ONBOARD_ARGS[@]}"
  ok "Onboard complete."
}

# ── Step 4: Patch model in config ─────────────────────────────────────────────
patch_model() {
  CONFIG_FILE="$HOME/.openclaw/openclaw.json"
  if [[ ! -f "$CONFIG_FILE" ]]; then
    warn "Config not found — skipping model patch."
    return 0
  fi

  info "Patching model to openai/${OPENAI_MODEL}..."
  node -e "
    const fs = require('fs');
    const cfg = JSON.parse(fs.readFileSync('$CONFIG_FILE', 'utf8'));
    cfg.agents = cfg.agents || {};
    cfg.agents.defaults = cfg.agents.defaults || {};
    cfg.agents.defaults.model = cfg.agents.defaults.model || {};
    cfg.agents.defaults.model.primary = 'openai/$OPENAI_MODEL';
    cfg.tools = cfg.tools || {};
    cfg.tools.profile = 'coding';
    fs.writeFileSync('$CONFIG_FILE', JSON.stringify(cfg, null, 2));
    console.log('Model patched: openai/$OPENAI_MODEL');
  "
}


# ── Main ──────────────────────────────────────────────────────────────────────
echo ""
echo -e "${CYAN}╔══════════════════════════════════════════════════╗${NC}"
echo -e "${CYAN}║     OpenClaw Real Agent Gateway Installer        ║${NC}"
echo -e "${CYAN}╚══════════════════════════════════════════════════╝${NC}"
echo ""

install_node
install_openclaw_cli
onboard_openclaw
patch_model

echo ""
ok "OpenClaw setup complete!"
echo ""
echo "  Gateway port:  $GATEWAY_PORT"
echo "  Model:         openai/$OPENAI_MODEL"
echo ""
echo "  The gateway starts automatically when Hosaka boots."
echo "  Or run 'openclaw gateway' manually to start it now."
echo ""
