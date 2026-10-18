#!/usr/bin/env bash
# User-level source install; appliance boot setup lives in scripts/setup_hosaka.sh.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PREFIX="${HOSAKA_PREFIX:-$HOME/.local}"
GUI=0
for arg in "$@"; do
  case "$arg" in
    --gui) GUI=1 ;;
    --help|-h)
      echo "Usage: bash install.sh [--gui]"
      echo "Installs Python dependencies, PicoClaw, and a source CLI under HOSAKA_PREFIX (default ~/.local)."
      exit 0 ;;
    *) echo "Unknown option: $arg" >&2; exit 2 ;;
  esac
done
[[ "$(id -u)" != 0 ]] || { echo "Run this installer as your normal user, not sudo." >&2; exit 1; }
TARGET="$PREFIX/bin/hosaka"
if [[ -e "$TARGET" ]] && ! grep -qF '# Hosaka source launcher' "$TARGET"; then
  echo "Refusing to replace a different Hosaka installation at $TARGET." >&2
  exit 1
fi
EXISTING="$(command -v hosaka || true)"
if [[ -n "$EXISTING" && "$EXISTING" != "$TARGET" ]]; then
  echo "Another hosaka is on PATH at $EXISTING. Remove it from PATH before installing from source." >&2
  exit 1
fi
PYTHON="${PYTHON:-python3}"
"$PYTHON" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' \
  || { echo "Python 3.10+ is required." >&2; exit 1; }
VENV="$ROOT/.venv"
[[ ! -x "$ROOT/.hosakavenv/bin/python" ]] || VENV="$ROOT/.hosakavenv"
[[ -x "$VENV/bin/python" ]] || "$PYTHON" -m venv "$VENV"
"$VENV/bin/python" -m pip install -r "$ROOT/requirements-hosaka.txt"
export PATH="$PREFIX/bin:$HOME/.local/bin:$PATH"
INSTALL_PICO=1
if command -v picoclaw >/dev/null 2>&1; then
  VERSION="$(picoclaw version | sed -nE 's/.*picoclaw v?([0-9]+\.[0-9]+\.[0-9]+).*/\1/p' | head -1)"
  [[ -n "$VERSION" ]] || { echo "Cannot determine the installed PicoClaw version; Hosaka requires 0.3.1+." >&2; exit 1; }
  if "$VENV/bin/python" -c 'import sys; sys.exit(0 if tuple(map(int, sys.argv[1].split("."))) >= (0, 3, 1) else 1)' "$VERSION"; then
    INSTALL_PICO=0
  fi
fi
if (( INSTALL_PICO )); then
  bash "$ROOT/scripts/install-picoclaw.sh" --prefix "$PREFIX" --no-runtime
fi
(cd "$ROOT" && "$VENV/bin/python" -m hosaka.paths init \
  --mode source --repo-root "$ROOT" --runtime-root "$ROOT" --launcher "$TARGET" \
  --python "$VENV/bin/python")
"$VENV/bin/python" "$ROOT/scripts/bootstrap_picoclaw_runtime.py" --home "$HOME" --seed-config
if (( GUI )); then
  command -v npm >/dev/null || { echo "Node.js/npm is required for --gui." >&2; exit 1; }
  (cd "$ROOT/frontend" && npm ci && npm run build:check)
  (cd "$ROOT/kiosk" && npm ci)
fi
mkdir -p "$PREFIX/bin"
TMP="$(mktemp "$PREFIX/bin/.hosaka-source.XXXXXX")"
trap 'rm -f "$TMP"' EXIT
{
  printf '#!/usr/bin/env bash\n# Hosaka source launcher\nset -euo pipefail\n'
  printf 'export HOSAKA_REPO=%q\n' "$ROOT"
  printf 'export HOSAKA_PREFIX=%q\n' "$PREFIX"
  printf 'export HOSAKA_SOURCE_INSTALL=1\n'
  if [[ -n "${HOSAKA_DATA_DIR+x}" ]]; then
    printf 'export HOSAKA_DATA_DIR=%q\n' "$HOSAKA_DATA_DIR"
  fi
  if [[ -n "${HOSAKA_GAMES_DIR+x}" ]]; then
    printf 'export HOSAKA_GAMES_DIR=%q\n' "$HOSAKA_GAMES_DIR"
  fi
  printf 'export PATH=%q:"$PATH"\n' "$PREFIX/bin"
  printf 'export HOSAKA_SOURCE_GUI=%s\n' "$GUI"
  printf 'exec bash "$HOSAKA_REPO/scripts/hosaka" "$@"\n'
} >"$TMP"
chmod 755 "$TMP"
mv "$TMP" "$TARGET"
case "${SHELL:-}" in
  */zsh) RC="$HOME/.zshrc" ;;
  */bash)
    if [[ "$(uname -s)" == Darwin ]]; then RC="$HOME/.bash_profile"; else RC="$HOME/.bashrc"; fi ;;
  *) RC="" ;;
esac
if [[ -n "$RC" ]]; then
  LINE="$(printf 'export PATH=%q:"$PATH"' "$PREFIX/bin")"
  if ! grep -qFx "$LINE" "$RC" 2>/dev/null; then
    printf '\n# Hosaka source installation\n%s\n' "$LINE" >>"$RC"
  fi
  printf 'Installed %s. Open a new terminal or run: source %q\n' "$TARGET" "$RC"
else
  printf 'Installed %s. Add to your shell PATH: %s\n' "$TARGET" "$PREFIX/bin"
fi
echo "Native paths: hosaka paths --json"
echo "Offline installation checks: hosaka doctor --offline"
echo "Next: hosaka tui   (starts in your current workspace)"
echo "A fresh install uses OpenAI gpt-4.1 and asks for its API key once, with hidden input."
echo "Existing provider choices are preserved. Use /select llm only to change providers."
