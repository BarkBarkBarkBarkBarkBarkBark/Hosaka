#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
COMPOSE_FILE="$REPO_ROOT/docker/compose.yml"
PROJECT_NAME="hosaka"

pass() { printf '[ok] %s\n' "$*"; }
fail() { printf '[fail] %s\n' "$*" >&2; exit 1; }
warn() { printf '[warn] %s\n' "$*"; }

dc() {
  docker compose -f "$COMPOSE_FILE" -p "$PROJECT_NAME" "$@"
}

require() {
  command -v "$1" >/dev/null 2>&1 || fail "missing required command: $1"
}

require docker
require curl
require python3

if ! dc ps --status running | grep -q 'hosaka-dev'; then
  fail "hosaka-dev is not running. Start it with ./docker/dev.sh up"
fi
pass "docker compose service is running"

curl -sf http://127.0.0.1:8421/progress >/dev/null || fail "/progress did not respond"
pass "/progress responded"

curl -sf http://127.0.0.1:8421/api/health >/dev/null || fail "/api/health did not respond"
pass "/api/health responded"

dc exec -T hosaka bash -lc 'command -v picoclaw >/dev/null' || fail "picoclaw missing in container"
pass "picoclaw present in container"

dc exec -T hosaka bash -lc 'command -v tailscale >/dev/null' || fail "tailscale missing in container"
pass "tailscale present in container"

dc exec -T hosaka bash -lc 'test -d /opt/hosaka-field-terminal/hosaka/web/ui' || fail "built UI missing in container"
pass "built UI present in container"

dc exec -T hosaka /opt/hosaka-field-terminal/.venv/bin/python - <<'PY' || fail "one or more HTTP checks failed inside container"
import json
import sys
import urllib.request

urls = [
    "http://127.0.0.1:8421/api/health",
    "http://127.0.0.1:8421/api/v1/health",
    "http://127.0.0.1:8421/api/beacon",
    "http://127.0.0.1:8421/api/v1/inbox/events",
]

for url in urls:
    with urllib.request.urlopen(url, timeout=5) as resp:
        if resp.status != 200:
            raise SystemExit(f"bad status for {url}: {resp.status}")
        print(json.dumps({"url": url, "status": resp.status}))
PY
pass "loopback HTTP checks passed inside container"

warn "docker initialization looks good"