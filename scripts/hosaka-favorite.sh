#!/usr/bin/env bash
# Open the operator's "favorite" — the quick-access target on the Hosaka
# right-click menu (desktop + SPA).
#
# Configured via ~/.config/hosaka/favorite, whose first line is either:
#   - a flatpak app id   (e.g. md.obsidian.Obsidian) → `flatpak run <id>`
#   - a raw command line (e.g. `lxterminal -e htop`)  → run as-is
# When unset, falls back to the Applications menu so the action is never dead.
set -u

CFG="${XDG_CONFIG_HOME:-$HOME/.config}/hosaka/favorite"
fav=""
[ -r "$CFG" ] && fav="$(head -n1 "$CFG" 2>/dev/null | tr -d '\r' | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//')"

if [ -z "$fav" ]; then
  command -v jgmenu_run >/dev/null 2>&1 && exec jgmenu_run apps
  exit 0
fi

case "$fav" in
  *" "*)
    # Has spaces → treat as a command line.
    exec sh -c "$fav"
    ;;
  *)
    # Single token → prefer a matching flatpak app, else run as a command.
    if command -v flatpak >/dev/null 2>&1 && flatpak info "$fav" >/dev/null 2>&1; then
      exec flatpak run "$fav"
    fi
    exec sh -c "$fav"
    ;;
esac
