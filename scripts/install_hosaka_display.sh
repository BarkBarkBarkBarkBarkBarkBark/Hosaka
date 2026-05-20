#!/usr/bin/env bash
# install_hosaka_display.sh — install and configure the X / Openbox /
# Chromium appliance display stack for Hosaka.
#
# Two profiles:
#
#   --profile display-manual   install the display dependencies but DO NOT
#                              autostart the GUI. Operator runs `hosaka wall
#                              start` by hand. This is the safe default for
#                              workstations and remote-managed Pis.
#
#   --profile display-kiosk    appliance mode. Boot directly into the
#                              Hosaka GUI (tty1 autologin -> hosaka-startx
#                              -> openbox -> Chromium). This writes:
#                                ~/.xinitrc
#                                /etc/X11/Xwrapper.config  (allowed_users=anybody)
#                                /etc/hosaka/env           (PATH/PICOCLAW_BIN)
#                                /etc/systemd/system/getty@tty1.service.d/autologin.conf
#                              The Xwrapper.config edit is needed because
#                              Xorg.wrap rejects "only console users are
#                              allowed to run the X server" otherwise. It is
#                              opt-in for appliance / display builds only.
#
# Renderers:
#
#   --renderer chromium        (default) stable on Pi; this is what the wall
#                              supervisor (scripts/hosaka-wall) drives.
#   --renderer electron        installs Electron deps too; only used when
#                              the operator explicitly wants Electron. The
#                              packet's hard lesson is that Electron SIGTRAPs
#                              on some Pi displays, so we never make it the
#                              default.
#
# Autologin:
#
#   --enable-tty1-autologin    write the systemd drop-in so tty1 logs in as
#                              the operator account at boot.
#   --no-autologin             leave tty1 untouched.
#
# All paths come from $HOME / $HOSAKA_DIRECTORY (resolved to absolute paths
# below). NO hardcoded /home/<user> values land in any generated file.

set -euo pipefail

PROFILE=""
RENDERER="chromium"
AUTOLOGIN="ask"

usage() {
  cat <<USAGE
install_hosaka_display.sh — Hosaka X/Openbox/Chromium appliance installer

Usage:
  scripts/install_hosaka_display.sh --profile display-manual|display-kiosk
                                    [--renderer chromium|electron]
                                    [--enable-tty1-autologin|--no-autologin]

Examples:
  # Workstation: install the bits, don't autostart anything
  scripts/install_hosaka_display.sh --profile display-manual

  # Pi appliance: full kiosk boot
  sudo HOSAKA_DIRECTORY=\$HOME/code/Hosaka \\
    scripts/install_hosaka_display.sh --profile display-kiosk \\
    --renderer chromium --enable-tty1-autologin
USAGE
}

while (( $# )); do
  case "$1" in
    --profile)
      [[ $# -ge 2 ]] || { echo "--profile needs a value" >&2; exit 2; }
      PROFILE="$2"; shift 2 ;;
    --profile=*) PROFILE="${1#*=}"; shift ;;
    --renderer)
      [[ $# -ge 2 ]] || { echo "--renderer needs a value" >&2; exit 2; }
      RENDERER="$2"; shift 2 ;;
    --renderer=*) RENDERER="${1#*=}"; shift ;;
    --enable-tty1-autologin) AUTOLOGIN="yes"; shift ;;
    --no-autologin)          AUTOLOGIN="no"; shift ;;
    -h|--help|help) usage; exit 0 ;;
    *) echo "unknown arg: $1" >&2; usage >&2; exit 2 ;;
  esac
done

case "$PROFILE" in
  display-manual|display-kiosk) : ;;
  "")  echo "missing --profile" >&2; usage >&2; exit 2 ;;
  *)   echo "unknown --profile: $PROFILE" >&2; exit 2 ;;
esac
case "$RENDERER" in
  chromium|electron) : ;;
  *) echo "unknown --renderer: $RENDERER" >&2; exit 2 ;;
esac

# ── soft-coded paths ────────────────────────────────────────────────────────
# TARGET_USER / TARGET_HOME so `sudo ./install_hosaka_display.sh` lands
# files in the operator's home, not root's.
TARGET_USER="${SUDO_USER:-$(id -un)}"
TARGET_HOME="$(getent passwd "$TARGET_USER" 2>/dev/null | cut -d: -f6)"
TARGET_HOME="${TARGET_HOME:-${HOME:-/root}}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="${HOSAKA_DIRECTORY:-${HOSAKA_REPO:-$(cd "$SCRIPT_DIR/.." && pwd)}}"
case "$REPO_ROOT" in
  /*) : ;;
  *) echo "HOSAKA_DIRECTORY/HOSAKA_REPO must be absolute, got: $REPO_ROOT" >&2; exit 2 ;;
esac

green='\033[0;32m'; cyan='\033[0;36m'; amber='\033[0;33m'; nc='\033[0m'
info() { printf "${cyan}[display]${nc} %s\n" "$*"; }
ok()   { printf "${green}[display]${nc} %s\n" "$*"; }
warn() { printf "${amber}[display]${nc} %s\n" "$*"; }

# ── apt packages ────────────────────────────────────────────────────────────
DISPLAY_PKGS=(
  xinit
  xserver-xorg
  xserver-xorg-legacy
  openbox
  xterm
  x11-utils
  x11-xserver-utils
  dbus-x11
  unclutter
)

info "installing display packages: ${DISPLAY_PKGS[*]} + chromium"
if command -v apt-get >/dev/null 2>&1; then
  sudo apt-get update -qq
  sudo apt-get install -y "${DISPLAY_PKGS[@]}" || warn "some display packages failed; continuing"
  # chromium ships under two different names depending on the distro.
  chromium_ok=0
  for pkg in chromium chromium-browser; do
    if sudo apt-get install -y "$pkg"; then
      ok "installed: $pkg"; chromium_ok=1; break
    fi
  done
  (( chromium_ok )) || warn "neither chromium nor chromium-browser is installable"
else
  warn "no apt-get found; skipping package install (assume packages present)"
fi

# ── install supervisor helpers into /usr/local/bin ──────────────────────────
for helper in hosaka-wall hosaka-startx; do
  if [[ -f "$REPO_ROOT/scripts/$helper" ]]; then
    sudo install -m 755 "$REPO_ROOT/scripts/$helper" "/usr/local/bin/$helper"
    ok "installed /usr/local/bin/$helper"
  fi
done

# ── /etc/hosaka/env (idempotent merge) ──────────────────────────────────────
# Don't blow away a richer file that install_hosaka.sh already wrote; just
# make sure the keys we need are present.
sudo mkdir -p /etc/hosaka
if [[ ! -f /etc/hosaka/env ]]; then
  sudo tee /etc/hosaka/env >/dev/null <<ENV
HOSAKA_REPO=$REPO_ROOT
HOSAKA_DIRECTORY=$REPO_ROOT
PICOCLAW_HOME=$TARGET_HOME/.picoclaw
PATH=$TARGET_HOME/.local/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
ENV
  ok "wrote /etc/hosaka/env"
else
  ok "/etc/hosaka/env already present (left untouched)"
fi

# ── ~/.xinitrc (only for the kiosk profile) ─────────────────────────────────
if [[ "$PROFILE" == "display-kiosk" && -f "$REPO_ROOT/dotfiles/xinitrc" ]]; then
  sudo install -D -m 755 -o "$TARGET_USER" -g "$TARGET_USER" \
    "$REPO_ROOT/dotfiles/xinitrc" "$TARGET_HOME/.xinitrc"
  ok "wrote $TARGET_HOME/.xinitrc"
fi

# ── /etc/X11/Xwrapper.config (kiosk only; appliance opt-in) ─────────────────
# Why: Xorg.wrap defaults to "only console users are allowed to run the X
# server", which makes hosaka-startx fail with that error message when
# launched via systemd autologin. The Pi appliance hardening packet calls
# this out explicitly. We only write it in kiosk mode so generic dev
# installs don't silently widen the X attack surface.
if [[ "$PROFILE" == "display-kiosk" ]]; then
  info "configuring /etc/X11/Xwrapper.config (kiosk mode requires non-console X)"
  sudo mkdir -p /etc/X11
  sudo tee /etc/X11/Xwrapper.config >/dev/null <<'XWRAP'
# Managed by scripts/install_hosaka_display.sh (kiosk profile).
# Hosaka boots tty1 autologin -> hosaka-startx, which is technically not a
# console user from Xorg.wrap's perspective. allowed_users=anybody widens
# that gate so the appliance can come up automatically. Only used for the
# appliance / kiosk display build; do not enable on a generic workstation.
allowed_users=anybody
needs_root_rights=yes
XWRAP
  ok "wrote /etc/X11/Xwrapper.config"
fi

# ── tty1 autologin (kiosk only, opt-in) ─────────────────────────────────────
if [[ "$PROFILE" == "display-kiosk" ]]; then
  if [[ "$AUTOLOGIN" == "ask" ]]; then
    # Default to ON for kiosk profile unless caller said --no-autologin.
    AUTOLOGIN="yes"
  fi
fi
if [[ "$AUTOLOGIN" == "yes" ]]; then
  info "writing getty@tty1 autologin drop-in for user=$TARGET_USER"
  sudo mkdir -p /etc/systemd/system/getty@tty1.service.d
  sudo tee /etc/systemd/system/getty@tty1.service.d/autologin.conf >/dev/null <<EOF
# Managed by scripts/install_hosaka_display.sh (display-kiosk profile).
# Autologins TARGET_USER on tty1 so hosaka-startx can run from .bash_profile.
# Shell escape: Ctrl+Alt+F2 gets you a real getty; Ctrl+Alt+F1 returns to GUI.
[Service]
ExecStart=
ExecStart=-/sbin/agetty --autologin $TARGET_USER --noclear %I \$TERM
EOF
  sudo systemctl daemon-reload
  sudo systemctl enable getty@tty1.service >/dev/null 2>&1 || true
  ok "tty1 autologin enabled for $TARGET_USER"

  # Drop a .bash_profile hook so the autologin shell on tty1 invokes
  # hosaka-startx exactly once. Other ttys are unaffected.
  PROFILE_HOOK="$TARGET_HOME/.bash_profile"
  if ! grep -q 'hosaka-startx' "$PROFILE_HOOK" 2>/dev/null; then
    sudo -u "$TARGET_USER" tee -a "$PROFILE_HOOK" >/dev/null <<'HOOK'

# Hosaka appliance: auto-start X on tty1 only. hosaka-startx itself refuses
# to run on any other tty, so this is safe to leave in place.
if [ -z "${DISPLAY:-}" ] && [ "$(tty)" = "/dev/tty1" ] && command -v hosaka-startx >/dev/null 2>&1; then
  exec hosaka-startx
fi
HOOK
    ok "appended hosaka-startx hook to $PROFILE_HOOK"
  fi
fi

# ── renderer guard ──────────────────────────────────────────────────────────
if [[ "$RENDERER" == "electron" ]]; then
  warn "selected --renderer electron — note that Electron SIGTRAPs on some Pi displays."
  warn "If the wall is unstable, hosaka-wall will fall back to Chromium via HOSAKA_KIOSK_RENDERER=chromium."
  sudo tee /etc/hosaka/env.renderer >/dev/null <<ENV
HOSAKA_KIOSK_RENDERER=electron
ENV
else
  sudo tee /etc/hosaka/env.renderer >/dev/null <<ENV
HOSAKA_KIOSK_RENDERER=chromium
HOSAKA_CHROMIUM_MODE=${HOSAKA_CHROMIUM_MODE:-kiosk}
ENV
fi

ok "display install complete (profile=$PROFILE, renderer=$RENDERER, autologin=$AUTOLOGIN)"
echo
echo "Next:"
case "$PROFILE" in
  display-manual)
    echo "  hosaka wall start         # bring up Chromium against the local backend"
    echo "  hosaka display doctor     # diagnose if it doesn't come up"
    ;;
  display-kiosk)
    echo "  sudo reboot               # appliance will boot directly into the wall"
    echo "  hosaka display doctor     # run from SSH if the wall stays dark"
    echo "  Ctrl+Alt+F2               # shell escape from the GUI"
    ;;
esac
