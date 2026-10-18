#!/bin/sh
set -eu

APP_ROOT="${APP_ROOT:-/opt/hosaka-field-terminal}"
PYTHON="$APP_ROOT/.venv/bin/python"
export HOSAKA_DATA_DIR="${HOSAKA_DATA_DIR:-$HOME/.hosaka}"
export HOSAKA_GAMES_DIR="${HOSAKA_GAMES_DIR:-$HOSAKA_DATA_DIR/games}"

if [ "${1:-}" = "migrate" ]; then
  exec "$PYTHON" -B -m hosaka "$@"
fi

"$PYTHON" -m hosaka.paths init --mode docker \
    --repo-root "$APP_ROOT" --runtime-root "$APP_ROOT" \
    --launcher /usr/local/bin/hosaka --python "$PYTHON" >/dev/null
"$PYTHON" "$APP_ROOT/scripts/bootstrap_picoclaw_runtime.py" --home "$HOME" --seed-config >/dev/null

if [ "${1:-}" = "--initialize-only" ]; then
    if [ "$#" != 1 ]; then
        echo "Usage: hosaka --initialize-only" >&2
        exit 2
    fi
    exit 0
fi

exec "$PYTHON" -m hosaka "$@"
