#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
SOURCE="$REPO_ROOT/scripts/hosaka"
USER_BIN="$HOME/.local/bin"
GLOBAL_BIN="/usr/local/bin"
INSTALL_MODE="local"

while (( $# )); do
  case "$1" in
    --global)
      INSTALL_MODE="global"
      shift
      ;;
    *)
      echo "unknown install-local-cli arg: $1" >&2
      exit 1
      ;;
  esac
done

if [[ ! -x "$SOURCE" ]]; then
  chmod +x "$SOURCE"
fi

repo_venv_activate="$REPO_ROOT/.venv/bin/activate"
repo_venv_cfg="$REPO_ROOT/.venv/pyvenv.cfg"
if [[ -f "$repo_venv_activate" ]]; then
  recorded_venv="$(grep -E '(^|[[:space:]])VIRTUAL_ENV=' "$repo_venv_activate" | head -n 1 | cut -d= -f2- | tr -d "'\"" || true)"
  if [[ -f "$repo_venv_cfg" ]]; then
    cfg_venv="$(sed -n 's/^command = .* -m venv //p' "$repo_venv_cfg" | head -n 1 || true)"
    if [[ -n "$cfg_venv" ]]; then
      recorded_venv="$cfg_venv"
    fi
  fi
  if [[ -n "$recorded_venv" && "$recorded_venv" != "$REPO_ROOT/.venv" ]]; then
    echo "warning: repo-local .venv looks relocated." >&2
    echo "warning: activate points at $recorded_venv, not $REPO_ROOT/.venv" >&2
    echo "warning: prefer a stable PATH target like ~/.local/bin, or recreate .venv in this checkout." >&2
  fi
fi

TARGET_DIR=""
if [[ "$INSTALL_MODE" == "global" ]]; then
  TARGET_DIR="$GLOBAL_BIN"
elif [[ -d "$USER_BIN" || ":$PATH:" == *":$USER_BIN:"* ]]; then
  mkdir -p "$USER_BIN"
  TARGET_DIR="$USER_BIN"
elif [[ -n "${VIRTUAL_ENV:-}" && -d "$VIRTUAL_ENV/bin" && ":$PATH:" == *":$VIRTUAL_ENV/bin:"* ]]; then
  TARGET_DIR="$VIRTUAL_ENV/bin"
else
  candidate="$REPO_ROOT"
  fallback_dir=""
  while [[ "$candidate" != "/" ]]; do
    if [[ -d "$candidate/.venv/bin" ]]; then
      fallback_dir="$candidate/.venv/bin"
      if [[ ":$PATH:" == *":$candidate/.venv/bin:"* ]]; then
        TARGET_DIR="$candidate/.venv/bin"
        break
      fi
    fi
    candidate="$(dirname "$candidate")"
  done

  if [[ -z "$TARGET_DIR" && -n "$fallback_dir" ]]; then
    TARGET_DIR="$fallback_dir"
  fi

  if [[ -z "$TARGET_DIR" ]]; then
    TARGET_DIR="$USER_BIN"
    mkdir -p "$TARGET_DIR"
  fi
fi

TARGET="$TARGET_DIR/hosaka"
if [[ "$INSTALL_MODE" == "global" ]]; then
  sudo mkdir -p "$TARGET_DIR"
  sudo ln -sfn "$SOURCE" "$TARGET"
  sudo chmod +x "$SOURCE" "$TARGET"
else
  ln -sfn "$SOURCE" "$TARGET"
  chmod +x "$SOURCE" "$TARGET"
fi

echo "hosaka command installed at: $TARGET"
echo "source path: $SOURCE"
if [[ "$INSTALL_MODE" != "global" && ":$PATH:" != *":$TARGET_DIR:"* ]]; then
  echo "note: $TARGET_DIR is not currently on PATH"
  echo "add this to your shell profile: export PATH=\"$TARGET_DIR:\$PATH\""
fi
