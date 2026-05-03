#!/usr/bin/env bash
# Install Picoclaw for the current user without sudo.
#
# Default target: ~/.local/bin/picoclaw
# This keeps laptop/dev setup low-friction and avoids mutating /usr/local/bin.

set -euo pipefail

PREFIX="${PICOCLAW_PREFIX:-$HOME/.local}"
RUN_ONBOARD=0
BOOTSTRAP_RUNTIME=1
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

usage() {
  cat <<USAGE
install-picoclaw.sh — install Picoclaw for this user

Usage:
  scripts/install-picoclaw.sh [--prefix DIR] [--onboard] [--no-runtime]

Options:
  --prefix DIR    install under DIR/bin (default: ~/.local)
  --onboard       run 'picoclaw onboard' after install
  --no-runtime    skip Hosaka runtime bootstrap into ~/.picoclaw/workspace

Examples:
  scripts/install-picoclaw.sh
  scripts/install-picoclaw.sh --onboard
USAGE
}

while (( $# )); do
  case "$1" in
    --prefix)
      [[ $# -ge 2 ]] || { echo "--prefix needs a value" >&2; exit 2; }
      PREFIX="$2"
      shift 2
      ;;
    --prefix=*)
      PREFIX="${1#*=}"
      shift
      ;;
    --onboard)
      RUN_ONBOARD=1
      shift
      ;;
    --no-runtime)
      BOOTSTRAP_RUNTIME=0
      shift
      ;;
    -h|--help|help)
      usage
      exit 0
      ;;
    *)
      echo "unknown arg: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

need() {
  command -v "$1" >/dev/null 2>&1 || { echo "missing required command: $1" >&2; exit 1; }
}

need curl
need tar
need mktemp

os="$(uname -s)"
arch="$(uname -m)"
case "$os:$arch" in
  Darwin:arm64) asset="picoclaw_Darwin_arm64.tar.gz" ;;
  Darwin:x86_64) asset="picoclaw_Darwin_x86_64.tar.gz" ;;
  Linux:aarch64|Linux:arm64) asset="picoclaw_Linux_arm64.tar.gz" ;;
  Linux:x86_64|Linux:amd64) asset="picoclaw_Linux_x86_64.tar.gz" ;;
  *)
    echo "unsupported platform: $os $arch" >&2
    echo "see https://github.com/sipeed/picoclaw/releases" >&2
    exit 1
    ;;
esac

install_dir="$PREFIX/bin"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

url="https://github.com/sipeed/picoclaw/releases/latest/download/$asset"
echo "› downloading $asset"
curl -fL "$url" -o "$tmp/picoclaw.tar.gz"

echo "› unpacking"
tar -xzf "$tmp/picoclaw.tar.gz" -C "$tmp"
bin="$(find "$tmp" -type f -name picoclaw -perm -111 | head -1 || true)"
if [[ -z "$bin" ]]; then
  bin="$(find "$tmp" -type f -name picoclaw | head -1 || true)"
fi
[[ -n "$bin" ]] || { echo "archive did not contain a picoclaw binary" >&2; exit 1; }

mkdir -p "$install_dir"
install -m 0755 "$bin" "$install_dir/picoclaw"
echo "✓ installed $install_dir/picoclaw"

case ":$PATH:" in
  *":$install_dir:"*) ;;
  *)
    echo "! $install_dir is not currently on PATH"
    if [[ -w "$HOME/.zshrc" || ! -e "$HOME/.zshrc" ]]; then
      if ! grep -qs 'HOME/.local/bin' "$HOME/.zshrc" 2>/dev/null; then
        printf '\n# Hosaka / Picoclaw\nexport PATH="$HOME/.local/bin:$PATH"\n' >> "$HOME/.zshrc"
        echo "✓ added ~/.local/bin to ~/.zshrc"
      fi
    fi
    export PATH="$install_dir:$PATH"
    ;;
esac

echo "› version"
"$install_dir/picoclaw" --version 2>/dev/null || "$install_dir/picoclaw" version 2>/dev/null || true

if (( BOOTSTRAP_RUNTIME )); then
  echo "› bootstrapping Hosaka runtime into ~/.picoclaw/workspace"
  py="${PYTHON:-python3}"
  if [[ -x "$REPO_ROOT/../.venv/bin/python" ]]; then
    py="$REPO_ROOT/../.venv/bin/python"
  elif [[ -x "$REPO_ROOT/.venv/bin/python" ]]; then
    py="$REPO_ROOT/.venv/bin/python"
  fi
  "$py" "$REPO_ROOT/scripts/bootstrap_picoclaw_runtime.py" --home "$HOME"
  echo "✓ runtime ready"
fi

if (( RUN_ONBOARD )); then
  echo "› running picoclaw onboard"
  echo "  if macOS kills this with exit 137, close memory-heavy apps and run: $install_dir/picoclaw onboard"
  "$install_dir/picoclaw" onboard
else
  echo "next: $install_dir/picoclaw onboard"
fi

echo "next: restart Hosaka with: hosaka dev -fresh"
