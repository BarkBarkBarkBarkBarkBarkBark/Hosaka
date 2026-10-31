#!/usr/bin/env bash
# Refresh the hosted field terminal from this canonical checkout.
# Operator packages and extension-data stay in ~/.hosaka and are not copied.
# Public workers keep HOSAKA_PUBLIC_MODE=1, so extension execution stays off.
set -euo pipefail

REPO_ROOT="${HOSAKA_REPO:-$(cd "$(dirname "$0")/.." && pwd)}"
case "$REPO_ROOT" in
  "$HOME/.hosaka"|"$HOME/.hosaka"/*)
    echo "refusing to publish the operator data root" >&2
    exit 1
    ;;
esac

find_field_terminal() {
  local candidate
  for candidate in \
    "$REPO_ROOT/../../hosaka_field-terminal" \
    "$REPO_ROOT/../hosaka_field-terminal" \
    "$REPO_ROOT/../hosaka-field-terminal"
  do
    if [[ -f "$candidate/fly.toml" && -f "$candidate/Dockerfile" ]]; then
      (cd "$candidate" && pwd)
      return 0
    fi
  done
  return 1
}

if [[ -n "${HOSAKA_FIELD_TERMINAL:-}" ]]; then
  FIELD="$HOSAKA_FIELD_TERMINAL"
else
  FIELD="$(find_field_terminal)" || {
    echo "no field terminal checkout; hosted refresh skipped"
    exit 0
  }
fi
mkdir -p "$FIELD"

OVERLAY="$FIELD/runtime-overlay"
rm -rf "$OVERLAY"
mkdir -p "$OVERLAY/examples"
rsync -a --delete \
  --exclude '__pycache__/' \
  --exclude '*.pyc' \
  --exclude '.venv/' \
  --exclude '.hosaka/' \
  --exclude 'extension-data/' \
  --exclude 'extensions.lock.json' \
  --exclude 'secrets.json' \
  --exclude '.env' \
  --exclude '.env.*' \
  "$REPO_ROOT/hosaka/" "$OVERLAY/hosaka/"
rsync -a --delete \
  --exclude '__pycache__/' \
  --exclude '*.pyc' \
  --exclude '.venv/' \
  --exclude '.hosaka/' \
  --exclude 'extension-data/' \
  --exclude 'secrets.json' \
  --exclude '.env' \
  --exclude '.env.*' \
  "$REPO_ROOT/examples/extensions/" "$OVERLAY/examples/extensions/"
cp "$REPO_ROOT/requirements-hosaka.txt" "$OVERLAY/requirements-hosaka.txt"
cat >"$OVERLAY/README" <<'EOF'
Staged by `hosaka update` from the canonical Hosaka checkout.
Operator extensions and extension-data are not part of this overlay.
EOF

if [[ -e "$OVERLAY/extension-data" || -e "$OVERLAY/extensions.lock.json" || -e "$OVERLAY/.hosaka" || -e "$OVERLAY/hosaka/secrets.json" ]]; then
  echo "refusing overlay that contains operator extension data" >&2
  exit 1
fi

if [[ -d "$FIELD/frontend" && -d "$REPO_ROOT/frontend/src" ]]; then
  rm -rf "$FIELD/frontend/src"
  cp -R "$REPO_ROOT/frontend/src" "$FIELD/frontend/src"
  cp "$REPO_ROOT/frontend/index.html" "$FIELD/frontend/index.html"
  mkdir -p "$FIELD/docs"
  if [[ -L "$FIELD/docs/api.md" ]]; then rm "$FIELD/docs/api.md"; fi
  cp "$REPO_ROOT/docs/api.md" "$FIELD/docs/api.md"
  rm -rf "$FIELD/frontend/public/locales" "$FIELD/frontend/public/library" "$FIELD/frontend/public/reading"
  cp -R "$REPO_ROOT/frontend/public/locales" "$FIELD/frontend/public/locales"
  cp -R "$REPO_ROOT/frontend/public/library" "$FIELD/frontend/public/library"
  if [[ -d "$REPO_ROOT/frontend/public/reading" ]]; then
    cp -R "$REPO_ROOT/frontend/public/reading" "$FIELD/frontend/public/reading"
  fi
  if [[ -f "$REPO_ROOT/frontend/public/splash.png" ]]; then
    cp "$REPO_ROOT/frontend/public/splash.png" "$FIELD/frontend/public/splash.png"
  fi
fi

echo "staged hosted runtime at $OVERLAY"
if [[ "${HOSAKA_HOSTED_DEPLOY:-1}" != "1" ]]; then
  echo "deploy skipped"
  exit 0
fi
if ! command -v fly >/dev/null 2>&1; then
  echo "fly CLI missing; runtime is staged. Install fly, then run hosaka update again."
  exit 0
fi
if [[ ! -f "$FIELD/fly.toml" ]]; then
  echo "field terminal has no fly.toml; runtime is staged" >&2
  exit 1
fi

APP="$(awk -F'"' '/^app / {print $2; exit}' "$FIELD/fly.toml")"
[[ -n "$APP" ]] || { echo "could not read fly app name" >&2; exit 1; }
LABEL="hosted-terminal-$(date -u +%Y%m%d%H%M%S)"
IMAGE="registry.fly.io/${APP}:${LABEL}"
(
  cd "$FIELD"
  fly deploy --build-only --push --remote-only --ha=false --yes \
    --image-label "$LABEL" --app "$APP"
)
fly secrets set --app "$APP" --stage "HOSAKA_WORKER_IMAGE=${IMAGE}"
fly deploy --image "$IMAGE" --app "$APP" --remote-only --ha=false --yes
echo "deployed ${IMAGE}"
