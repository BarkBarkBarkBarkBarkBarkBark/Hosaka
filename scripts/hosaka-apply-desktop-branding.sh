#!/usr/bin/env bash
# Apply the Hosaka-branded LXQt desktop base layer.
#
# LXQt is only the substrate: Hosaka should open on top. When the operator
# intentionally drops to desktop, this wallpaper + right-click menu make the
# desktop feel like Hosaka's app drawer instead of a random Linux session.
set -u

LOG="/tmp/hosaka-desktop-branding.log"
SETTINGS="${HOME}/.config/pcmanfm-qt/lxqt/settings.conf"
WALLPAPER_DST="${HOME}/.local/share/hosaka/desktop-background.png"

log() { printf '%s %s\n' "$(date '+%H:%M:%S')" "$*" >>"$LOG" 2>/dev/null || true; }

repo_root() {
  for candidate in "${HOSAKA_REPO:-}" "/opt/hosaka-field-terminal" "${HOME}/Hosaka" "/home/operator/Hosaka"; do
    [ -n "$candidate" ] && [ -f "$candidate/dotfiles/wallpaper/hosaka-desktop.png" ] && {
      printf '%s\n' "$candidate"
      return 0
    }
  done
  return 1
}

ROOT="$(repo_root || true)"
if [ -n "$ROOT" ]; then
  mkdir -p "$(dirname "$WALLPAPER_DST")" 2>/dev/null || true
  cp "$ROOT/dotfiles/wallpaper/hosaka-desktop.png" "$WALLPAPER_DST" 2>/dev/null || true
fi

mkdir -p "$(dirname "$SETTINGS")" 2>/dev/null || true
cat >"$SETTINGS" <<EOF
[Desktop]
# Hosaka desktop substrate. Right-click forwards to Openbox's Hosaka menu.
Wallpaper=${WALLPAPER_DST}
WallpaperMode=crop
BgColor=#0b0d10
ShowWmMenu=true
EOF

if [ -f "$WALLPAPER_DST" ]; then
  if command -v pcmanfm-qt >/dev/null 2>&1; then
    pcmanfm-qt --profile=lxqt --set-wallpaper="$WALLPAPER_DST" --wallpaper-mode=crop >/dev/null 2>&1 || true
  fi
  log "wallpaper set to $WALLPAPER_DST"
else
  log "wallpaper missing; wrote settings only"
fi

# Big one-click launcher on the desktop + app menu.
ICON_SRC=""
DESKTOP_SRC=""
if [ -n "$ROOT" ]; then
  [ -f "$ROOT/dotfiles/icons/hosaka.png" ] && ICON_SRC="$ROOT/dotfiles/icons/hosaka.png"
  [ -f "$ROOT/dotfiles/applications/hosaka.desktop" ] && DESKTOP_SRC="$ROOT/dotfiles/applications/hosaka.desktop"
fi
if [ -n "$ICON_SRC" ]; then
  mkdir -p "${HOME}/.local/share/icons/hicolor/256x256/apps" "${HOME}/.local/share/hosaka" 2>/dev/null || true
  cp "$ICON_SRC" "${HOME}/.local/share/hosaka/hosaka-icon.png" 2>/dev/null || true
  cp "$ICON_SRC" "${HOME}/.local/share/icons/hicolor/256x256/apps/hosaka.png" 2>/dev/null || true
  gtk-update-icon-cache -f "${HOME}/.local/share/icons/hicolor" >/dev/null 2>&1 || true
fi
if [ -n "$DESKTOP_SRC" ]; then
  mkdir -p "${HOME}/.local/share/applications" "${HOME}/Desktop" 2>/dev/null || true
  cp "$DESKTOP_SRC" "${HOME}/.local/share/applications/hosaka.desktop" 2>/dev/null || true
  cp "$DESKTOP_SRC" "${HOME}/Desktop/hosaka.desktop" 2>/dev/null || true
  chmod +x "${HOME}/.local/share/applications/hosaka.desktop" "${HOME}/Desktop/hosaka.desktop" 2>/dev/null || true
  gio set "${HOME}/Desktop/hosaka.desktop" metadata::trusted true >/dev/null 2>&1 || true
fi
