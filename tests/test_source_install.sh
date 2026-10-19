#!/usr/bin/env bash
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
export TEST_PYTHON="${TEST_PYTHON:-$(command -v python3)}"
temp="$(mktemp -d)"
trap 'rm -rf "$temp"' EXIT
mkdir -p "$temp/repo/scripts" "$temp/repo/hosaka" "$temp/repo/frontend" "$temp/repo/kiosk" "$temp/home" "$temp/bin"
cp "$root/install.sh" "$temp/repo/install.sh"
cp "$root/scripts/hosaka" "$temp/repo/scripts/hosaka"
cp "$root/hosaka/paths.py" "$temp/repo/hosaka/paths.py"
cp -R "$root/hosaka/extensions" "$temp/repo/hosaka/extensions"
cp -R "$root/examples" "$temp/repo/examples"
touch "$temp/repo/requirements-hosaka.txt"
cat >"$temp/bin/python3" <<'SH'
#!/bin/bash
if [[ "$*" == "-c "* && "$*" == *"sys.version_info"* ]]; then
  if [[ "${TEST_SYSTEM_OLD:-0}" == 1 ]]; then
    case "$0" in */python3|*/python3.14|*/python3.13) exit 1 ;; esac
  fi
  [[ ! -f "$(dirname "$0")/old-python" ]]
elif [[ "$*" == "-m venv "* ]]; then
  mkdir -p "$3/bin"
  cp "$0" "$3/bin/python"
elif [[ "$*" == *"-m hosaka tui"* ]]; then
  printf 'TUI_CWD=%s\n' "$PWD"
  printf 'PYTHONPATH=%s\n' "$PYTHONPATH"
elif [[ "$*" == *"-m hosaka.paths"* || "$*" == *"-m hosaka.extensions"* ]]; then
  exec "$TEST_PYTHON" "$@"
fi
SH
cp "$temp/bin/python3" "$temp/bin/python3.12"
cp "$temp/bin/python3" "$temp/bin/python3.13"
cp "$temp/bin/python3" "$temp/bin/python3.14"
printf '#!/bin/sh\nexit "${TEST_NODE_STATUS:-0}"\n' >"$temp/bin/node"
printf '#!/bin/sh\nprintf "%%s:%%s\\n" "$PWD" "$*" >>"$NPM_CALLS"\n' >"$temp/bin/npm"
printf '#!/bin/sh\necho "picoclaw 0.3.1"\n' >"$temp/bin/picoclaw"
chmod +x "$temp/bin/"*
export HOME="$temp/home" SHELL=/bin/zsh HOSAKA_PREFIX="$temp/prefix"
export NPM_CALLS="$temp/npm-calls"
export PATH="$temp/bin:/usr/bin:/bin"
unset FLATPAK_ID
TEST_SYSTEM_OLD=1 bash "$temp/repo/install.sh" >"$temp/install-output"
grep -q 'Using Python: python3.12' "$temp/install-output"
grep -q 'Next: hosaka dev' "$temp/install-output"
grep -q 'frontend:ci' "$NPM_CALLS"
grep -q 'frontend:run build:check' "$NPM_CALLS"
grep -q 'kiosk:ci' "$NPM_CALLS"
grep -q 'HOSAKA_SOURCE_GUI=1' "$HOSAKA_PREFIX/bin/hosaka"
touch "$temp/repo/.venv/bin/old-python"
TEST_SYSTEM_OLD=1 bash "$temp/repo/install.sh" >"$temp/install-output"
grep -q 'Preserved incompatible Python environment' "$temp/install-output"
test ! -f "$temp/repo/.venv/bin/old-python"
test -f "$temp/repo/".venv.python-backup.*/bin/old-python
before="$(wc -l <"$NPM_CALLS")"
TEST_NODE_STATUS=1 bash "$temp/repo/install.sh" --tui >"$temp/install-output"
[[ "$(wc -l <"$NPM_CALLS")" == "$before" ]]
grep -q 'Next: hosaka tui' "$temp/install-output"
grep -q 'HOSAKA_SOURCE_GUI=0' "$HOSAKA_PREFIX/bin/hosaka"
if TEST_NODE_STATUS=1 bash "$temp/repo/install.sh" --gui >"$temp/install-output" 2>&1; then
  echo "Source installer accepted an unsupported Node.js" >&2
  exit 1
fi
grep -q 'sudo dnf module install nodejs:22/common' "$temp/install-output"
if PYTHON=/missing/python bash "$temp/repo/install.sh" --tui >"$temp/install-output" 2>&1; then
  echo "Source installer accepted an invalid explicit Python" >&2
  exit 1
fi
grep -q 'sudo dnf install python3.12' "$temp/install-output"
if FLATPAK_ID=com.visualstudio.code bash "$temp/repo/install.sh" >"$temp/install-output" 2>&1; then
  echo "Source installer accepted a Flatpak sandbox" >&2
  exit 1
fi
grep -q 'flatpak-spawn --host bash' "$temp/install-output"
test -x "$HOSAKA_PREFIX/bin/hosaka"
test -f "$HOME/.hosaka/installation.json"
test -d "$HOME/.hosaka/extensions"
test -f "$HOME/.hosaka/extensions/reference-extension/extension.yaml"
test -f "$HOME/.hosaka/extensions.lock.json"
grep -q 'Hosaka source installation' "$HOME/.zshrc"
mkdir -p "$temp/project"
result="$(cd "$temp/project" && "$HOSAKA_PREFIX/bin/hosaka" tui)"
[[ "$result" == *"TUI_CWD=$temp/project"* ]]
[[ "$result" == *"PYTHONPATH=$temp/repo"* ]]
result="$(cd "$temp/project" && "$HOSAKA_PREFIX/bin/hosaka" extensions create cli-example --path "my extension" --json)"
test -f "$temp/project/my extension/extension.yaml"
[[ "$result" == *"cli-example"* ]]
bash "$temp/repo/install.sh"
[[ "$(grep -c 'Hosaka source installation' "$HOME/.zshrc")" == 1 ]]
printf 'owner code\n' >"$HOME/.hosaka/extensions/owner.py"
printf '\n# owner customization\n' >>"$HOME/.hosaka/extensions/reference-extension/main.py"
bash "$temp/repo/install.sh"
grep -q 'owner code' "$HOME/.hosaka/extensions/owner.py"
grep -q 'owner customization' "$HOME/.hosaka/extensions/reference-extension/main.py"
HOSAKA_DATA_DIR="$temp/custom data" HOSAKA_GAMES_DIR="$temp/custom games" bash "$temp/repo/install.sh"
test -f "$temp/custom data/installation.json"
result="$(cd "$temp/project" && "$HOSAKA_PREFIX/bin/hosaka" paths --json)"
[[ "$result" == *"/custom data"* ]]
[[ "$result" == *"/custom games/roms/psx"* ]]
cp "$temp/custom data/extensions/reference-extension/extension.yaml" "$temp/reference-manifest.backup"
printf 'invalid: [\n' >"$temp/custom data/extensions/reference-extension/extension.yaml"
if HOSAKA_DATA_DIR="$temp/custom data" HOSAKA_GAMES_DIR="$temp/custom games" bash "$temp/repo/install.sh"; then
  echo "Source installer reported success with an invalid reference extension" >&2
  exit 1
fi
cp "$temp/reference-manifest.backup" "$temp/custom data/extensions/reference-extension/extension.yaml"
printf '#!/bin/sh\n# Docker client\n' >"$HOSAKA_PREFIX/bin/hosaka"
if bash "$temp/repo/install.sh"; then
  echo "Source install overwrote another installation" >&2
  exit 1
fi
echo "Source installation regression tests passed"
