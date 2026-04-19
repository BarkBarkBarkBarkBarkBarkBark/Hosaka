#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────────────────
# smoke_test.sh — Hosaka appliance health check suite
#
# Run on the Pi after install, or remotely via SSH:
#   ./scripts/smoke_test.sh
#   ssh pi@<pi-ip> /opt/hosaka-field-terminal/scripts/smoke_test.sh
#
# Exit code: 0 if all critical checks pass, 1 if any fail.
# Warnings (non-critical) don't affect exit code.
# ──────────────────────────────────────────────────────────────────────────────
set -euo pipefail

WEB_PORT="${HOSAKA_WEB_PORT:-8421}"
WEB_HOST="${HOSAKA_WEB_HOST:-127.0.0.1}"

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

PASS=0
FAIL=0
WARN=0

pass() { echo -e "  ${GREEN}✓${NC} $*"; ((PASS++)) || true; }
fail() { echo -e "  ${RED}✗${NC} $*"; ((FAIL++)) || true; }
warn() { echo -e "  ${YELLOW}?${NC} $*"; ((WARN++)) || true; }
section() { echo -e "\n${CYAN}── $* ──${NC}"; }

echo ""
echo -e "${CYAN}╔══════════════════════════════════════════════════╗"
echo -e "║     HOSAKA SMOKE TEST                            ║"
echo -e "╚══════════════════════════════════════════════════╝${NC}"

# ── network reachability ──────────────────────────────────────────────────────
section "network"

if ping -c 3 -W 2 8.8.8.8 >/dev/null 2>&1; then
  pass "internet reachable (8.8.8.8)"
else
  fail "internet NOT reachable — check network config"
fi

if ping -c 2 -W 2 api.openai.com >/dev/null 2>&1; then
  pass "api.openai.com reachable"
else
  fail "api.openai.com NOT reachable — LLM will fail"
fi

if ping -c 2 -W 2 tailscale.com >/dev/null 2>&1; then
  pass "tailscale.com reachable"
else
  warn "tailscale.com not reachable (optional)"
fi

# ── tailscale ─────────────────────────────────────────────────────────────────
section "tailscale"

if command -v tailscale >/dev/null 2>&1; then
  TS_STATUS=$(tailscale status --json 2>/dev/null | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('BackendState','unknown'))" 2>/dev/null || echo "error")
  if [[ "$TS_STATUS" == "Running" ]]; then
    TS_IP=$(tailscale ip -4 2>/dev/null || echo "n/a")
    pass "tailscale running — IP: $TS_IP"
  else
    warn "tailscale installed but not running (state=$TS_STATUS)"
  fi
else
  warn "tailscale not installed (optional — run with INSTALL_TAILSCALE=1)"
fi

# ── hosaka web server ─────────────────────────────────────────────────────────
section "hosaka web server (http://${WEB_HOST}:${WEB_PORT})"

if curl -sf --max-time 5 "http://${WEB_HOST}:${WEB_PORT}/api/health" -o /tmp/hosaka_health.json; then
  pass "/api/health responded"

  # Parse health JSON
  HEALTH=$(cat /tmp/hosaka_health.json)
  UI_BUILT=$(echo "$HEALTH" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('ui_built', False))" 2>/dev/null || echo "false")
  PICOCLAW=$(echo "$HEALTH" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('picoclaw_bin', False))" 2>/dev/null || echo "false")
  OPENAI=$(echo "$HEALTH" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('openai_key', False))" 2>/dev/null || echo "false")

  if [[ "$UI_BUILT" == "True" ]]; then
    pass "SPA UI built and present"
  else
    warn "SPA UI not built — run frontend build step"
  fi

  if [[ "$OPENAI" == "True" ]]; then
    pass "OPENAI_API_KEY is set"
  else
    fail "OPENAI_API_KEY is NOT set — add to /opt/hosaka-field-terminal/.env"
  fi

  if [[ "$PICOCLAW" == "True" ]]; then
    pass "picoclaw binary found"
  else
    warn "picoclaw not found — agent features disabled (OpenAI fallback active)"
  fi
else
  fail "hosaka web server NOT responding on port ${WEB_PORT}"
  warn "start with: sudo systemctl start hosaka-webserver"
fi

# ── OpenAI API key sanity ─────────────────────────────────────────────────────
section "openai api"

OPENAI_KEY="${OPENAI_API_KEY:-}"
if [[ -z "$OPENAI_KEY" ]] && [[ -f /opt/hosaka-field-terminal/.env ]]; then
  # Try to source the env file
  OPENAI_KEY=$(grep -E '^OPENAI_API_KEY=' /opt/hosaka-field-terminal/.env 2>/dev/null | cut -d= -f2- | tr -d '"' || echo "")
fi

if [[ -z "$OPENAI_KEY" ]]; then
  fail "OPENAI_API_KEY not found in env or .env file"
else
  HTTP_STATUS=$(curl -sf --max-time 8 -o /dev/null -w "%{http_code}" \
    https://api.openai.com/v1/models \
    -H "Authorization: Bearer ${OPENAI_KEY}" 2>/dev/null || echo "000")
  if [[ "$HTTP_STATUS" == "200" ]]; then
    pass "OpenAI API key valid (200 OK)"
  elif [[ "$HTTP_STATUS" == "401" ]]; then
    fail "OpenAI API key is INVALID (401)"
  else
    warn "OpenAI API key check returned HTTP $HTTP_STATUS (network issue?)"
  fi
fi

# ── picoclaw ──────────────────────────────────────────────────────────────────
section "picoclaw"

if command -v picoclaw >/dev/null 2>&1; then
  PCVER=$(picoclaw --version 2>/dev/null || echo "unknown")
  pass "picoclaw found: $PCVER"
else
  warn "picoclaw not installed — /agent commands will use OpenAI fallback"
fi

# ── FTP connectivity ──────────────────────────────────────────────────────────
section "ftp (passive connectivity test)"

if curl -sf --max-time 8 ftp://ftp.dlptest.com/ | head -3 >/dev/null 2>&1; then
  pass "FTP passive test passed (ftp.dlptest.com)"
else
  warn "FTP test failed or timed out (non-critical for most setups)"
fi

# ── docker ───────────────────────────────────────────────────────────────────
section "docker (optional)"

if command -v docker >/dev/null 2>&1; then
  if docker run --rm hello-world >/dev/null 2>&1; then
    pass "docker hello-world OK"
  else
    warn "docker installed but hello-world failed — check permissions (try: sudo usermod -aG docker \$USER)"
  fi
else
  warn "docker not installed (optional)"
fi

# ── chromium (kiosk) ──────────────────────────────────────────────────────────
section "chromium kiosk"

hosaka_chromium_bin() {
  local c
  for c in hosaka-kiosk-chromium chromium-browser chromium; do
    if command -v "$c" >/dev/null 2>&1; then
      command -v "$c"
      return 0
    fi
  done
  return 1
}

CH="$(hosaka_chromium_bin 2>/dev/null || true)"
if [[ -n "$CH" ]]; then
  pass "chromium launcher found at $CH"
  ver="$("$CH" --version 2>&1 | head -1 || true)"
  if [[ -n "$ver" ]]; then
    pass "chromium --version: $ver"
  else
    warn "chromium --version returned empty"
  fi
  # Headless launch is fragile on some ARM images; timeout + no-sandbox keeps this diagnostic-only.
  if timeout 25s "$CH" --headless=new --disable-gpu --no-sandbox --virtual-time-budget=3000 about:blank >/dev/null 2>&1; then
    pass "chromium headless smoke OK (about:blank)"
  else
    warn "chromium headless smoke failed or timed out — kiosk may still work on a real DISPLAY"
  fi
else
  warn "no chromium — try: sudo apt-get install -y chromium  OR  chromium-browser"
fi

if command -v unclutter >/dev/null 2>&1; then
  pass "unclutter found (cursor hiding)"
else
  warn "unclutter not installed — run: sudo apt-get install -y unclutter"
fi

# ── systemd services ──────────────────────────────────────────────────────────
section "systemd services"

for svc in hosaka-webserver hosaka-kiosk; do
  if systemctl is-active --quiet "${svc}.service" 2>/dev/null; then
    pass "${svc}.service is running"
  elif systemctl list-unit-files --quiet "${svc}.service" >/dev/null 2>&1; then
    warn "${svc}.service is installed but not running"
  else
    warn "${svc}.service not installed yet"
  fi
done

# ── summary ───────────────────────────────────────────────────────────────────
echo ""
echo -e "${CYAN}────────────────────────────────────────────────────${NC}"
echo -e "  ${GREEN}${PASS} passed${NC}  ${YELLOW}${WARN} warnings${NC}  ${RED}${FAIL} failed${NC}"
echo ""

if [[ $FAIL -gt 0 ]]; then
  echo -e "  ${RED}✗ smoke test FAILED — address the issues above.${NC}"
  exit 1
else
  echo -e "  ${GREEN}✓ smoke test PASSED — signal steady.${NC}"
  exit 0
fi
