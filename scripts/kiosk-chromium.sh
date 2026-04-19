#!/usr/bin/env bash
# Launch whichever Chromium .deb actually ships on this OS (Bookworm+ uses "chromium").
set -euo pipefail
for name in chromium-browser chromium; do
  if cmd=$(command -v "$name" 2>/dev/null); then
    exec "$cmd" "$@"
  fi
done
echo "hosaka-kiosk-chromium: no chromium or chromium-browser in PATH" >&2
exit 127
