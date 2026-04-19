#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────────────────
# setup_tailscale_sshfs.sh — Mac-side helper: mount Pi filesystem via SSHFS
# over Tailscale for remote editing in VS Code / Cursor.
#
# Usage (Mac):
#   ./scripts/setup_tailscale_sshfs.sh              # interactive — prompts for Pi IP
#   HOSAKA_PI_IP=100.x.x.x ./scripts/setup_tailscale_sshfs.sh
#   HOSAKA_PI_IP=100.x.x.x HOSAKA_PI_USER=pi ./scripts/setup_tailscale_sshfs.sh unmount
#
# Requirements (Mac):
#   brew install macfuse
#   brew install gromgit/fuse/sshfs-mac    # or: brew install --cask macfuse && brew install sshfs
# ──────────────────────────────────────────────────────────────────────────────
set -euo pipefail

PI_USER="${HOSAKA_PI_USER:-pi}"
PI_IP="${HOSAKA_PI_IP:-}"
REMOTE_PATH="/opt/hosaka-field-terminal"
MOUNT_POINT="${HOSAKA_MOUNT:-$HOME/mnt/hosaka-pi}"

GREEN='\033[0;32m'
CYAN='\033[0;36m'
YELLOW='\033[1;33m'
NC='\033[0m'

info()  { echo -e "${CYAN}[hosaka-sshfs]${NC} $*"; }
ok()    { echo -e "${GREEN}[hosaka-sshfs]${NC} $*"; }
warn()  { echo -e "${YELLOW}[hosaka-sshfs]${NC} $*"; }

ACTION="${1:-mount}"

# ── preflight ─────────────────────────────────────────────────────────────────

if ! command -v sshfs >/dev/null 2>&1; then
  echo ""
  warn "sshfs not found. Install it first:"
  echo "  brew install macfuse"
  echo "  brew install gromgit/fuse/sshfs-mac"
  echo ""
  echo "  (You may need to allow macFUSE in System Settings > Privacy & Security)"
  exit 1
fi

if [[ "$ACTION" == "unmount" ]]; then
  info "Unmounting $MOUNT_POINT ..."
  umount "$MOUNT_POINT" 2>/dev/null || diskutil unmount "$MOUNT_POINT" 2>/dev/null || true
  ok "Unmounted."
  exit 0
fi

# ── resolve Pi IP ─────────────────────────────────────────────────────────────

if [[ -z "$PI_IP" ]]; then
  # Try to find it via Tailscale
  if command -v tailscale >/dev/null 2>&1; then
    FOUND=$(tailscale status --json 2>/dev/null \
      | python3 -c "
import sys, json
d = json.load(sys.stdin)
for peer in d.get('Peer', {}).values():
    hn = peer.get('HostName','').lower()
    if 'hosaka' in hn or 'raspberry' in hn or 'pi' in hn:
        ips = peer.get('TailscaleIPs', [])
        if ips: print(ips[0]); break
" 2>/dev/null || true)
    if [[ -n "$FOUND" ]]; then
      PI_IP="$FOUND"
      info "Auto-detected Pi at $PI_IP via Tailscale"
    fi
  fi

  if [[ -z "$PI_IP" ]]; then
    echo -n "Enter Pi Tailscale IP (e.g. 100.x.x.x): "
    read -r PI_IP
  fi
fi

# ── mount ─────────────────────────────────────────────────────────────────────

mkdir -p "$MOUNT_POINT"

info "Mounting ${PI_USER}@${PI_IP}:${REMOTE_PATH} → ${MOUNT_POINT}"

sshfs \
  "${PI_USER}@${PI_IP}:${REMOTE_PATH}" \
  "$MOUNT_POINT" \
  -o reconnect,ServerAliveInterval=15,ServerAliveCountMax=3,defer_permissions,volname=hosaka-pi

ok "Mounted at $MOUNT_POINT"
echo ""
echo "  Open in VS Code:  code $MOUNT_POINT"
echo "  Unmount:          $0 unmount"
echo ""
echo "  Tip: set HOSAKA_PI_IP=${PI_IP} in your shell profile to skip the prompt."
