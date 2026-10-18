#!/usr/bin/env bash
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
export TEST_PYTHON="${TEST_PYTHON:-$(command -v python3)}"
temp="$(mktemp -d)"
trap 'rm -rf "$temp"' EXIT
mkdir -p "$temp/repo/scripts" "$temp/repo/hosaka" "$temp/home" "$temp/bin"
cp "$root/install.sh" "$temp/repo/install.sh"
cp "$root/scripts/hosaka" "$temp/repo/scripts/hosaka"
cp "$root/hosaka/paths.py" "$temp/repo/hosaka/paths.py"
touch "$temp/repo/requirements-hosaka.txt"
cat >"$temp/bin/python3" <<'SH'
#!/bin/bash
if [[ "$*" == "-m venv "* ]]; then
  mkdir -p "$3/bin"
  cp "$0" "$3/bin/python"
elif [[ "$*" == *"-m hosaka tui"* ]]; then
  printf 'TUI_CWD=%s\n' "$PWD"
  printf 'PYTHONPATH=%s\n' "$PYTHONPATH"
elif [[ "$*" == *"-m hosaka.paths"* ]]; then
  exec "$TEST_PYTHON" "$@"
fi
SH
printf '#!/bin/sh\necho "picoclaw 0.3.1"\n' >"$temp/bin/picoclaw"
chmod +x "$temp/bin/"*
export HOME="$temp/home" SHELL=/bin/zsh HOSAKA_PREFIX="$temp/prefix"
export PATH="$temp/bin:/usr/bin:/bin"
bash "$temp/repo/install.sh"
test -x "$HOSAKA_PREFIX/bin/hosaka"
test -f "$HOME/.hosaka/installation.json"
test -d "$HOME/.hosaka/extensions"
grep -q 'Hosaka source installation' "$HOME/.zshrc"
mkdir -p "$temp/project"
result="$(cd "$temp/project" && "$HOSAKA_PREFIX/bin/hosaka" tui)"
[[ "$result" == *"TUI_CWD=$temp/project"* ]]
[[ "$result" == *"PYTHONPATH=$temp/repo"* ]]
bash "$temp/repo/install.sh"
[[ "$(grep -c 'Hosaka source installation' "$HOME/.zshrc")" == 1 ]]
printf 'owner code\n' >"$HOME/.hosaka/extensions/owner.py"
bash "$temp/repo/install.sh"
grep -q 'owner code' "$HOME/.hosaka/extensions/owner.py"
HOSAKA_DATA_DIR="$temp/custom data" HOSAKA_GAMES_DIR="$temp/custom games" bash "$temp/repo/install.sh"
test -f "$temp/custom data/installation.json"
result="$(cd "$temp/project" && "$HOSAKA_PREFIX/bin/hosaka" paths --json)"
[[ "$result" == *"/custom data"* ]]
[[ "$result" == *"/custom games/roms/psx"* ]]
printf '#!/bin/sh\n# Docker client\n' >"$HOSAKA_PREFIX/bin/hosaka"
if bash "$temp/repo/install.sh"; then
  echo "Source install overwrote another installation" >&2
  exit 1
fi
echo "Source installation regression tests passed"
