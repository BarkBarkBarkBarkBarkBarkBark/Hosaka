#!/usr/bin/env bash
# Copy this native checkout to the cyberdeck. No Docker image.
# A 1GB Pi does not run npm; build the terminal UI on a larger machine.
set -euo pipefail

REPO_ROOT="${HOSAKA_REPO:-$(cd "$(dirname "$0")/.." && pwd)}"
HOST="${HOSAKA_DECK_HOST:-hosaka}"
REMOTE="${HOSAKA_DECK_REPO:-/home/operator/Hosaka}"

case "$REPO_ROOT" in
  "$HOME/.hosaka"|"$HOME/.hosaka"/*)
    echo "refusing to publish the operator data root" >&2
    exit 1
    ;;
esac

mem_kb="${HOSAKA_MEM_TOTAL_KB:-}"
if [[ -z "$mem_kb" && -r /proc/meminfo ]]; then
  mem_kb="$(awk '/MemTotal:/ {print $2}' /proc/meminfo)"
fi
if [[ "$mem_kb" =~ ^[0-9]+$ ]] && (( mem_kb > 0 && mem_kb <= 1572864 )); then
  echo "This 1GB deck does not build the UI or use a Docker image. Run hosaka update from a larger machine." >&2
  exit 1
fi

echo "building terminal UI on this machine"
( cd "$REPO_ROOT/frontend" && npm run build )

echo "copying native tree to $HOST:$REMOTE"
rsync -a --delete \
  --exclude '.git/' \
  --exclude 'node_modules/' \
  --exclude '.venv/' \
  --exclude '.hosakavenv/' \
  --exclude '__pycache__/' \
  --exclude '*.pyc' \
  --exclude '.hosaka/' \
  --exclude 'extension-data/' \
  --exclude '.env' \
  --exclude '.env.*' \
  --exclude 'secrets.json' \
  "$REPO_ROOT/" "$HOST:$REMOTE/"

if [[ -d "$HOME/.hosaka/extensions" ]]; then
  echo "copying extension packages; extension-data stays on each machine"
  rsync -a \
    --exclude '.venv/' \
    --exclude '.web-venv/' \
    --exclude '__pycache__/' \
    --exclude '*.pyc' \
    --exclude '.env' \
    --exclude '.env.*' \
    --exclude 'secrets.json' \
    --exclude 'extension-data/' \
    "$HOME/.hosaka/extensions/" "$HOST:.hosaka/extensions/"
fi

REMOTE_PARENT="$(dirname "$REMOTE")"
for sibling in hosaka-gateway hosaka_citations virgo_zone; do
  if [[ -d "$REPO_ROOT/../$sibling" ]]; then
    echo "copying $sibling to $HOST:$REMOTE_PARENT/$sibling"
    rsync -a --delete \
      --exclude '.git/' \
      --exclude 'node_modules/' \
      --exclude '.next/' \
      --exclude '.vercel/' \
      --exclude '.venv/' \
      --exclude '.web-venv/' \
      --exclude '__pycache__/' \
      --exclude '*.pyc' \
      --exclude '*.db*' \
      --exclude '*.sqlite3*' \
      --exclude 'data/' \
      --exclude '.env' \
      --exclude '.env.*' \
      --exclude 'secrets.json' \
      "$REPO_ROOT/../$sibling/" "$HOST:$REMOTE_PARENT/$sibling/"
  fi
done

echo "deploying on the deck without npm or Docker"
ssh -o BatchMode=yes -o ConnectTimeout=8 "$HOST" \
  "HOSAKA_SKIP_UI_BUILD=1 HOSAKA_REPO=$(printf '%q' "$REMOTE") bash $(printf '%q' "$REMOTE")/scripts/hosaka update local --foreground"
