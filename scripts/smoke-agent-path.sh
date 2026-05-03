#!/usr/bin/env bash
# Smoke-test the full local Hosaka text → Picoclaw path.
# Safe: does not print API keys and does not mutate config.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="${PYTHON:-python3}"
if [[ -x "$REPO_ROOT/../.venv/bin/python" ]]; then
  PY="$REPO_ROOT/../.venv/bin/python"
elif [[ -x "$REPO_ROOT/.venv/bin/python" ]]; then
  PY="$REPO_ROOT/.venv/bin/python"
fi

FRONTEND_PORT="${HOSAKA_DEV_PORT:-5173}"
BACKEND_PORT="${HOSAKA_BACKEND_PORT:-8421}"
PICO_HOME="${PICOCLAW_HOME:-$HOME/.picoclaw}"
PICO_BIN="${PICOCLAW_BIN:-picoclaw}"

ok() { printf '✓ %s\n' "$*"; }
note() { printf '› %s\n' "$*"; }
warn() { printf '! %s\n' "$*"; }
fail() { printf '✗ %s\n' "$*" >&2; exit 1; }

need() {
  command -v "$1" >/dev/null 2>&1 || fail "missing command: $1"
}

note "repo: $REPO_ROOT"
note "python: $PY"
note "backend: http://127.0.0.1:$BACKEND_PORT"
note "frontend: http://127.0.0.1:$FRONTEND_PORT"
note "picoclaw home: $PICO_HOME"

need curl

if ! command -v "$PICO_BIN" >/dev/null 2>&1 && [[ ! -x "$PICO_BIN" ]]; then
  fail "picoclaw binary not found. Run: $REPO_ROOT/scripts/configure-picoclaw.sh --no-onboard"
fi
ok "picoclaw binary found: $(command -v "$PICO_BIN" 2>/dev/null || printf '%s' "$PICO_BIN")"

note "picoclaw status"
PICOCLAW_HOME="$PICO_HOME" "$PICO_BIN" --no-color status | sed -n '1,40p'

note "direct picoclaw one-shot"
direct_out="$(PICOCLAW_HOME="$PICO_HOME" "$PICO_BIN" --no-color agent --session hosaka-smoke-direct --message 'say signal steady and nothing else' 2>&1 || true)"
printf '%s\n' "$direct_out" | sed -n '1,80p'
grep -qi 'signal steady' <<<"$direct_out" || fail "direct picoclaw did not return signal steady"
ok "direct picoclaw replied"

note "port listeners"
if command -v lsof >/dev/null 2>&1; then
  lsof -nP -iTCP:"$BACKEND_PORT" -sTCP:LISTEN || warn "nothing listening on backend port $BACKEND_PORT"
  lsof -nP -iTCP:"$FRONTEND_PORT" -sTCP:LISTEN || warn "nothing listening on frontend port $FRONTEND_PORT"
else
  warn "lsof missing; skipping listener details"
fi

note "backend health"
health="$(curl -fsS "http://127.0.0.1:$BACKEND_PORT/api/health" || true)"
[[ -n "$health" ]] || fail "backend health is not reachable; run: $REPO_ROOT/scripts/hosaka dev -fresh"
printf '%s\n' "$health" | "$PY" -m json.tool | sed -n '1,80p' || printf '%s\n' "$health"
ok "backend health reachable"

note "backend in-process websocket smoke"
(
  cd "$REPO_ROOT"
  "$PY" - <<'PY'
from fastapi.testclient import TestClient
from hosaka.web.server import app
client = TestClient(app)
with client.websocket_connect('/ws/agent') as ws:
    hello = ws.receive_json()
    print('HELLO', hello)
    ws.send_json({'message': 'say signal steady and nothing else'})
    print('FRAME', ws.receive_json())
    reply = ws.receive_json()
    print('REPLY', reply)
    if 'signal steady' not in (reply.get('text') or '').lower():
        raise SystemExit('in-process websocket did not return signal steady')
PY
)
ok "backend in-process websocket replied"

note "live websocket smoke: backend :$BACKEND_PORT and vite proxy :$FRONTEND_PORT"
(
  cd "$REPO_ROOT"
  HOSAKA_BACKEND_PORT="$BACKEND_PORT" HOSAKA_DEV_PORT="$FRONTEND_PORT" "$PY" - <<'PY'
import asyncio
import json
import os
import sys
try:
    import websockets
except ImportError as exc:
    raise SystemExit('missing Python package websockets in this environment') from exc

backend_port = int(os.environ['HOSAKA_BACKEND_PORT'])
frontend_port = int(os.environ['HOSAKA_DEV_PORT'])

async def probe(url: str) -> None:
    print('URL', url)
    async with websockets.connect(url, open_timeout=4) as ws:
        print('HELLO', await asyncio.wait_for(ws.recv(), timeout=4))
        await ws.send(json.dumps({'message': 'say signal steady and nothing else'}))
        print('FRAME', await asyncio.wait_for(ws.recv(), timeout=4))
        reply_raw = await asyncio.wait_for(ws.recv(), timeout=35)
        print('REPLY', reply_raw)
        reply = json.loads(reply_raw)
        if 'signal steady' not in (reply.get('text') or '').lower():
            raise SystemExit(f'{url} did not return signal steady')
        await ws.send(json.dumps({'type': 'shell', 'cmd': 'pwd; command -v picoclaw; picoclaw --version || picoclaw version'}))
        shell_raw = await asyncio.wait_for(ws.recv(), timeout=12)
        print('SHELL', shell_raw)
        shell = json.loads(shell_raw)
        if shell.get('type') != 'shell_reply' or shell.get('exit') != 0:
            raise SystemExit(f'{url} shell smoke failed')

async def main() -> None:
    await probe(f'ws://127.0.0.1:{backend_port}/ws/agent')
    await probe(f'ws://127.0.0.1:{frontend_port}/ws/agent')

asyncio.run(main())
PY
)
ok "live backend/proxy websocket replied"

note "recent backend agent log lines"
if [[ -f "$REPO_ROOT/logs/dev/backend.log" ]]; then
  grep -E 'agent ws (message|reply)|picoclaw not ready|error' "$REPO_ROOT/logs/dev/backend.log" | tail -40 || warn "no agent lines found in logs/dev/backend.log"
else
  warn "no logs/dev/backend.log"
fi

ok "agent path smoke complete"
